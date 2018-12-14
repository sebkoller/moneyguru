#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "amount.h"
#include "split.h"
#include "transaction.h"
#include "account.h"

// NOTE ABOUT DECREF AND ERRORS
//
// When I started writing this unit, I took care of properly decrefing stuff
// in error conditions, but now I don't bother because this is not a library
// and this is not permanent: those errors are never supposed to happen. I
// write the "return NULL" to avoid segfaults and thus allow better debugging.
// but we don't care about memory leaks in this context.

/* Types */
static PyObject *UnsupportedCurrencyError = NULL;

typedef struct {
    PyObject_HEAD
    Amount amount;
} PyAmount;

static PyObject *Amount_Type;
#define Amount_Check(v) (Py_TYPE(v) == (PyTypeObject *)Amount_Type)

/* Represents an account (in the "accounting" sense).  Accounts in moneyGuru
 * don't hold much information (Transaction holds the bulk of a document's
 * juicy information). It's there as a unique identifier to assign Split to.
 * Initialization argument simply set initial values for their relevant
 * attributes, `name`, `currency` and `type`.
 */
typedef struct {
    PyObject_HEAD
    Account account;
    // EntryList belonging to that account. This list is computed from
    // `Document.transactions` by the Oven.
    PyObject *entries;
} PyAccount;

static PyObject *Account_Type;
#define Account_Check(v) (Py_TYPE(v) == (PyTypeObject *)Account_Type)

// Assignment of money to an Account within a Transaction.
typedef struct {
    PyObject_HEAD
    Split split;
    PyAccount *account;
    // Freeform memo about that split.
    PyObject *memo;
    // Unique reference from an external source.
    PyObject *reference;
} PySplit;

static PyObject *Split_Type;
#define Split_Check(v) (Py_TYPE(v) == (PyTypeObject *)Split_Type)

/* Wrapper around a Split to show in an Account ledger.
 *
 * The two main roles of the entry as a wrapper is to handle user edits and
 * show running totals for the account.
 *
 * All initialization arguments are directly assigned to their relevant
 * attributes in the entry. Most entries are created by the Oven, which does
 * the necessary calculations to compute running total information that the
 * entry needs on init.
 */
typedef struct {
    PyObject_HEAD
    // The split that we wrap
    PySplit *split;
    // The txn it's associated to
    PyObject *transaction;
    // The running total of all preceding entries in the account.
    Amount balance;
    // The running total of all preceding *reconciled* entries in the account.
    Amount reconciled_balance;
    // Running balance which includes all Budget spawns.
    Amount balance_with_budget;
    // Index in the EntryList. Set by `EntryList.add_entry` and used as a tie
    // breaker in case we have more than one entry from the same transaction.
    int index;
} PyEntry;

static PyObject *Entry_Type;
#define Entry_Check(v) (Py_TYPE(v) == (PyTypeObject *)Entry_Type)

typedef struct {
    PyObject_HEAD
    PyObject *entries;
    PyEntry *last_reconciled;
} PyEntryList;

static PyObject *EntryList_Type;

/* Utils */
static PyObject*
time2pydate(time_t date)
{
    if (date == 0) {
        Py_RETURN_NONE;
    }
    struct tm *d = gmtime(&date);
    return PyDate_FromDate(d->tm_year + 1900, d->tm_mon + 1, d->tm_mday);
}

static time_t
pydate2time(PyObject *pydate)
{
    // Special case: all return values are proper time values **except** 1
    // which means an error (0 means no date).
    struct tm date = {0};

    if (pydate == Py_None) {
        return 0;
    }
    if (!PyDate_Check(pydate)) {
        PyErr_SetString(PyExc_ValueError, "pydate2tm needs a date value");
        return 1;
    }
    date.tm_year = PyDateTime_GET_YEAR(pydate) - 1900;
    date.tm_mon = PyDateTime_GET_MONTH(pydate) - 1;
    date.tm_mday = PyDateTime_GET_DAY(pydate);
    return mktime(&date);
}

/* Frees a string created through strset()
 *
 * Returns false on error
 */
static bool
strfree(char **dst)
{
    if (dst == NULL) {
        // not supposed to happen
        return false;
    }
    if (*dst == NULL || *dst[0] == '\0') {
        // nothing to free
        return true;
    }
    free(*dst);
    *dst = NULL;
    return true;
}

/* Sets `dst` to the UTF-8 repr of `src`.
 *
 * This manages lifecycle of `dst`: it mallocs and frees `dst`, except when
 * `dst` is "", then it doesn't free it. Symmetrically, when `src` is empty,
 * we set `dst` to "", a static value, not mallocated.
 *
 * If `dst` points to NULL, we consider us to be in a "initial set" situation,
 * so we free nothing.
 *
 * Returns false on error.
 */
static bool
strset(char **dst, PyObject *src)
{
    if (!strfree(dst)) {
        return false;
    }
    if (src == Py_None) {
        *dst = NULL;
        return true;
    }
    Py_ssize_t len;
    char *s = PyUnicode_AsUTF8AndSize(src, &len);
    if (s == NULL) {
        return false;
    }
    if (len) {
        *dst = malloc(len+1);
        strncpy(*dst, s, len+1);
    } else {
        *dst = "";
    }
    return true;
}

static PyObject*
strget(const char *src)
{
    if (src == NULL) {
        Py_RETURN_NONE;
    } else if (src[0] == '\0') {
        return PyUnicode_InternFromString("");
    } else {
        return PyUnicode_FromString(src);
    }
}

static bool
strclone(char **dst, const char *src)
{
    if (!strfree(dst)) {
        return false;
    }
    if (src == NULL) {
        *dst = NULL;
        return true;
    }
    int len = strlen(src);
    if (len) {
        *dst = malloc(len+1);
        strncpy(*dst, src, len+1);
    } else {
        *dst = "";
    }
    return true;
}

static Currency*
getcur(const char *code)
{
    Currency *res;

    res = currency_get(code);
    if (res == NULL) {
        PyErr_SetString(PyExc_ValueError, "Wrong currency code");
        return NULL;
    }
    return res;
}

static Amount*
get_amount(PyObject *amount)
{
    /* Returns amount's ival if it's an amount, or 0 if it's an int with a value of 0.
       Call check_amount() before using this.
    */
    if (Amount_Check(amount)) {
        return &((PyAmount *)amount)->amount;
    }
    else { /* it's an int and it *has* to be 0 */
        return amount_zero();
    }
}

static bool
amounts_are_compatible(PyObject *a, PyObject *b)
{
    return amount_check(get_amount(a), get_amount(b));
}

static bool
check_amount(PyObject *o)
{
    /* Returns true if o is an amount and false otherwise.
       A valid amount is either an PyAmount instance or an int instance with the value of 0.
    */
    if (Amount_Check(o)) {
        return true;
    }
    if (!PyLong_Check(o)) {
        return false;
    }
    return PyLong_AS_LONG(o) == 0;
}

static bool
check_amounts(PyObject *a, PyObject *b, bool seterr)
{
    /* Verify that a and b are amounts and compatible together and returns true or false.
       if seterr is true, an appropriate error is set.
    */
    if (!check_amount(a) || !check_amount(b)) {
        if (seterr) {
            PyErr_SetString(PyExc_TypeError, "Amounts can only be compared with other amounts or zero.");
        }
        return false;
    }

    if (!amounts_are_compatible(a, b)) {
        if (seterr) {
            PyErr_SetString(PyExc_ValueError, "Amounts of different currencies can't be compared.");
        }
        return false;
    }

    return true;
}

static bool
strisblank(const char *s)
{
    while (*s != '\0') {
        if (!isblank(*s)) {
            return false;
        }
        s++;
    }
    return true;
}

static bool
strisexpr(const char *s)
{
    static const char exprchars[] = "+-/*()";
    while (*s != '\0') {
        if (strchr(exprchars, *s) != NULL) {
            return true;
        }
        s++;
    }
    return false;
}

static bool
same_currency(Amount *a, Amount *b)
{
    // Weird rules, but well...
    if (a->currency == NULL || b->currency == NULL) {
        return true;
    } else {
        return a->currency == b->currency;
    }
}

/* Currency functions */
static PyObject*
py_currency_global_init(PyObject *self, PyObject *args)
{
    char *dbpath;

    if (!PyArg_ParseTuple(args, "s", &dbpath)) {
        return NULL;
    }

    currency_global_init(dbpath);
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject*
py_currency_global_reset_currencies(PyObject *self, PyObject *args)
{
    currency_global_reset_currencies();
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject*
py_currency_register(PyObject *self, PyObject *args)
{
    char *code;
    int exponent;
    PyObject *py_startdate, *py_stopdate;
    time_t start_date, stop_date;
    double startrate, latestrate;

    if (!PyArg_ParseTuple(args, "siOdOd", &code, &exponent, &py_startdate, &startrate, &py_stopdate, &latestrate)) {
        return NULL;
    }

    start_date = pydate2time(py_startdate);
    if (start_date == 1) {
        return NULL;
    }
    stop_date = pydate2time(py_stopdate);
    if (stop_date == 1) {
        return NULL;
    }
    currency_register(code, exponent, start_date, startrate, stop_date, latestrate);
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject*
py_currency_getrate(PyObject *self, PyObject *args)
{
    PyObject *pydate;
    char *code1, *code2;
    Currency *c1, *c2;
    double rate;

    if (!PyArg_ParseTuple(args, "Oss", &pydate, &code1, &code2)) {
        return NULL;
    }

    time_t date = pydate2time(pydate);
    if (date == 1) {
        return NULL;
    }

    c1 = currency_get(code1);
    c2 = currency_get(code2);
    if (c1 == NULL || c2 == NULL) {
        // Something's wrong, let's just return 1
        return PyLong_FromLong(1);
    }
    if (currency_getrate(date, c1, c2, &rate) != CURRENCY_OK) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return PyFloat_FromDouble(rate);
}

static PyObject*
py_currency_set_CAD_value(PyObject *self, PyObject *args)
{
    PyObject *pydate;
    char *code;
    Currency *c;
    double rate;

    if (!PyArg_ParseTuple(args, "Osd", &pydate, &code, &rate)) {
        return NULL;
    }

    time_t date = pydate2time(pydate);
    if (date == 1) {
        return NULL;
    }

    c = getcur(code);
    if (c == NULL) {
        return NULL;
    }

    currency_set_CAD_value(date, c, rate);
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject*
py_currency_daterange(PyObject *self, PyObject *args)
{
    char *code;
    Currency *c;
    time_t start = 0;
    time_t stop = 0;
    PyObject *pystart, *pystop, *res;

    if (!PyArg_ParseTuple(args, "s", &code)) {
        return NULL;
    }

    c = currency_get(code);
    if (c == NULL) {
        // Invalid currency, return None
        Py_INCREF(Py_None);
        return Py_None;
    }

    if (!currency_daterange(c, &start, &stop)) {
        // No range, return None
        Py_INCREF(Py_None);
        return Py_None;
    }

    pystart = time2pydate(start);
    pystop = time2pydate(stop);
    res = PyTuple_Pack(2, pystart, pystop);
    Py_DECREF(pystart);
    Py_DECREF(pystop);
    return res;
}

/* Amount Methods */

static PyObject *
create_amount(int64_t ival, Currency *currency)
{
    /* Create a new amount in a way that is faster than the normal init */
    PyAmount *r;

    r = (PyAmount *)PyType_GenericAlloc((PyTypeObject *)Amount_Type, 0);
    r->amount.val = ival;
    r->amount.currency = currency;
    return (PyObject *)r;
}

static int
PyAmount_init(PyAmount *self, PyObject *args, PyObject *kwds)
{
    PyObject *amount;
    const char *code;
    double dtmp;
    Currency *c;

    static char *kwlist[] = {"amount", "currency", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "Os", kwlist, &amount, &code)) {
        return -1;
    }

    c = getcur(code);
    if (c == NULL) {
        return -1;
    }
    self->amount.currency = c;
    dtmp = PyFloat_AsDouble(amount);
    if (PyErr_Occurred()) {
        return -1;
    }
    self->amount.val = round(dtmp * pow(10, self->amount.currency->exponent));
    return 0;
}

static PyObject *
PyAmount_copy(PyObject *self)
{
    return create_amount(
        ((PyAmount *)self)->amount.val,
        ((PyAmount *)self)->amount.currency);
}

static PyObject *
PyAmount_deepcopy(PyObject *self, PyObject *args, PyObject *kwds)
{
    return PyAmount_copy(self);
}

static PyObject *
PyAmount_repr(PyAmount *self)
{
    PyObject *r, *fmt, *args;

    args = Py_BuildValue(
        "(is)", self->amount.val, self->amount.currency->code);
    fmt = PyUnicode_FromString("Amount(%r, %r)");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static Py_hash_t
PyAmount_hash(PyAmount *self)
{
    PyObject *hash_tuple, *int_value, *byte_value;
    Py_hash_t r;

    int_value = PyLong_FromLongLong(self->amount.val);
    byte_value = PyBytes_FromString(self->amount.currency->code);
    hash_tuple = PyTuple_Pack(2, int_value, byte_value);
    Py_DECREF(int_value);
    Py_DECREF(byte_value);
    r = PyObject_Hash(hash_tuple);
    Py_DECREF(hash_tuple);
    return r;
}

static PyObject *
PyAmount_richcompare(PyObject *a, PyObject *b, int op)
{
    int64_t aval, bval;
    int r, is_eq_op;

    is_eq_op = (op == Py_EQ) || (op == Py_NE);

    if (!check_amounts(a, b, !is_eq_op)) {
        if (op == Py_EQ) {
            Py_RETURN_FALSE;
        }
        else if (op == Py_NE) {
            Py_RETURN_TRUE;
        }
        else {
            return NULL; // An error has been set already
        }
    }

    /* The comparison is valid, do it */
    r = 0;
    aval = get_amount(a)->val;
    bval = get_amount(b)->val;
    switch (op) {
        case Py_LT: r = aval < bval; break;
        case Py_LE: r = aval <= bval; break;
        case Py_EQ: r = aval == bval; break;
        case Py_NE: r = aval != bval; break;
        case Py_GT: r = aval > bval; break;
        case Py_GE: r = aval >= bval; break;
    }
    if (r) {
        Py_RETURN_TRUE;
    }
    else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PyAmount_neg(PyAmount* self)
{
    return create_amount(-self->amount.val, self->amount.currency);
}

static int
PyAmount_bool(PyAmount *self)
{
    return self->amount.val != 0;
}

static PyObject *
PyAmount_abs(PyAmount* self)
{
    if (self->amount.val >= 0) {
        Py_INCREF(self);
        return (PyObject *)self;
    }
    else {
        return PyAmount_neg(self);
    }
}

static PyObject *
PyAmount_float(PyAmount* self)
{
    double dtmp;

    if (self->amount.val) {
        dtmp = (double)self->amount.val / pow(10, self->amount.currency->exponent);
    } else {
        dtmp = 0;
    }
    return PyFloat_FromDouble(dtmp);
}

static PyObject *
PyAmount_add(PyObject *a, PyObject *b)
{
    int64_t aval, bval;

    if (!check_amounts(a, b, true)) {
        return NULL;
    }
    aval = get_amount(a)->val;
    bval = get_amount(b)->val;
    if (aval && bval) {
        return create_amount(aval + bval, ((PyAmount *)a)->amount.currency);
    }
    else if (aval) {
        /* b is 0, return a */
        Py_INCREF(a);
        return a;
    }
    else {
        /* whether b is 0 or not, we return it */
        Py_INCREF(b);
        return b;
    }
}

static PyObject *
PyAmount_sub(PyObject *a, PyObject *b)
{
    int64_t aval, bval;

    if (!check_amounts(a, b, 1)) {
        return NULL;
    }
    aval = get_amount(a)->val;
    bval = get_amount(b)->val;
    if (aval && bval) {
        return create_amount(aval - bval, ((PyAmount *)a)->amount.currency);
    }
    else if (aval) {
        /* b is 0, return a */
        Py_INCREF(a);
        return a;
    }
    else if (bval) {
        /* a is 0 but not b, return -b */
        return PyAmount_neg((PyAmount *)b);
    }
    else {
        /* both a and b are 0, return any */
        Py_INCREF(a);
        return a;
    }
}

static PyObject *
PyAmount_mul(PyObject *a, PyObject *b)
{
    double dval;
    int64_t ival;

    /* first, for simplicity, handle reverse op */
    if (!Amount_Check(a) && Amount_Check(b)) {
        return PyAmount_mul(b, a);
    }
    /* it is assumed that a is an amount */
    if (Amount_Check(b)) {
        PyErr_SetString(PyExc_TypeError, "Can't multiply two amounts together");
        return NULL;
    }

    dval = PyFloat_AsDouble(b);
    if (dval == -1 && PyErr_Occurred()) {
        return NULL;
    }

    if (dval == 0) {
        return PyLong_FromLong(0);
    }

    ival = rint(((PyAmount *)a)->amount.val * dval);
    return create_amount(ival, ((PyAmount *)a)->amount.currency);
}

static PyObject *
PyAmount_true_divide(PyObject *a, PyObject *b)
{
    double dval;
    int64_t ival;

    if (!Amount_Check(a)) {
        PyErr_SetString(PyExc_TypeError, "An amount can't divide something else.");
        return NULL;
    }

    if (Amount_Check(b)) {
        if (!amounts_are_compatible(a, b)) {
            PyErr_SetString(PyExc_ValueError, "Amounts of different currency can't be divided.");
            return NULL;
        }
        // Return both rval divided together
        PyObject *rval1, *rval2;
        rval1 = PyAmount_float((PyAmount *)a);
        if (rval1 == NULL) {
            return NULL;
        }
        rval2 = PyAmount_float((PyAmount *)b);
        if (rval2 == NULL) {
            Py_DECREF(rval1);
            return NULL;
        }

        PyObject *res = PyNumber_TrueDivide(rval1, rval2);
        Py_DECREF(rval1);
        Py_DECREF(rval2);
        return res;
    }
    else {
        dval = PyFloat_AsDouble(b);
        if (dval == -1 && PyErr_Occurred()) {
            return NULL;
        }
    }

    if (dval == 0) {
        PyErr_SetString(PyExc_ZeroDivisionError, "");
        return NULL;
    }

    ival = rint(((PyAmount *)a)->amount.val / dval);
    return create_amount(ival, ((PyAmount *)a)->amount.currency);
}

static PyObject *
PyAmount_getcurrency_code(PyAmount *self)
{
    int len;
    len = strlen(self->amount.currency->code);
    return PyUnicode_DecodeASCII(self->amount.currency->code, len, NULL);
}

/* Amount Functions */
static PyObject*
py_amount_format(PyObject *self, PyObject *args, PyObject *kwds)
{
    int rc;
    Amount *amount;
    PyObject *pyamount;
    const char *default_currency = "";
    const char *zero_currency = "";
    int blank_zero = false;
    bool show_currency = false;
    const char *decimal_sep = ".";
    const char *grouping_sep = "";
    Currency *c = NULL;
    char result[64];
    static char *kwlist[] = {
        "amount", "default_currency", "blank_zero", "zero_currency",
        "decimal_sep", "grouping_sep", NULL};

    rc = PyArg_ParseTupleAndKeywords(
        args, kwds, "O|spsss", kwlist, &pyamount, &default_currency,
        &blank_zero, &zero_currency, &decimal_sep, &grouping_sep);
    if (!rc) {
        return NULL;
    }
    if (pyamount == Py_None) {
        // special case, always blank
        blank_zero = true;
    }

    // We don't support (yet) multibyte decimal sep and grouping sep. Let's
    // normalize that case.
    if (strlen(decimal_sep) > 1) {
        decimal_sep = ".";
    }
    if (strlen(grouping_sep) > 1) {
        grouping_sep = " ";
    }

    amount = get_amount(pyamount);
    if (!amount->val) {
        if (strlen(zero_currency)) {
            c = getcur(zero_currency);
            if (c == NULL) {
                return NULL;
            }
            amount->currency = c;
        } else {
            amount->currency = NULL;
        }
    }
    if (strlen(default_currency)) {
        c = getcur(default_currency);
        if (c == NULL) {
            return NULL;
        }
        show_currency = c != amount->currency;
    } else {
        show_currency = amount->currency != NULL;
    }
    rc = amount_format(
        result, amount, show_currency, blank_zero, decimal_sep[0],
        grouping_sep[0]);
    if (!rc) {
        PyErr_SetString(PyExc_ValueError, "something went wrong");
        return NULL;
    }
    rc = strlen(result);
    return PyUnicode_DecodeUTF8(result, rc, NULL);
}

/* Returns an `Amount` from `string`.
 *
 * We can parse strings like "42.54 cad" or "CAD 42.54".
 *
 * If `default_currency` is set, we can parse amounts that don't contain a
 * currency code and will give the amount that currency.
 *
 * If `with_expression` is true, we can parse stuff like "42*4 cad" or "usd
 * (1+2)/3". If you know your string doesn't contain any expression, turn this
 * flag off to greatly speed up parsing.
 *
 * `auto_decimal_place` allows for quick decimal-less typing. We assume that
 * the number has been typed to the last precision digit and automatically
 * place our decimal separator if there isn't one. For example, "1234" would be
 * parsed as "12.34" in a CAD context (in BHD, a currency with 3 digits, it
 * would be parsed as "1.234"). This doesn't work with expressions.
 *
 * With `strict_currency` enabled, `UnsupportedCurrencyError` is raised if an
 * unsupported currency is specified. We still parse sucessfully if no currency
 * is specified and `default_currency` is not `None`.
 */

static PyObject*
py_amount_parse(PyObject *self, PyObject *args, PyObject *kwds)
{
    int rc;
    char *s;
    char *default_currency = NULL;
    int with_expression = true;
    int auto_decimal_place = false;
    int strict_currency = false;
    Currency *c;
    uint8_t exponent;
    char grouping_sep;
    int64_t val;
    static char *kwlist[] = {
        "string", "default_currency", "with_expression", "auto_decimal_place",
        "strict_currency", NULL};

    // We encode as latin-1 for two reasons: first, we don't expect characters
    // outside this range. Second, keeping the default utf-8 makes us end up
    // with multi-byte characters in the case of the \xa0 non-beakable space.
    // Let's avoid that trouble.
    rc = PyArg_ParseTupleAndKeywords(
        args, kwds, "es|zppp", kwlist, "latin-1", &s, &default_currency,
        &with_expression, &auto_decimal_place, &strict_currency);
    if (!rc) {
        return NULL;
    }

    if (strisblank(s)) {
        PyMem_Free(s);
        return PyLong_FromLong(0);
    }

    c = amount_parse_currency(s, default_currency, strict_currency);
    if ((c == NULL) && strict_currency) {
        PyMem_Free(s);
        PyErr_SetString(UnsupportedCurrencyError, "no specified currency");
        return NULL;
    }

    if (c != NULL) {
        exponent = c->exponent;
    } else {
        // our only way not to error-out is to parse a zero
        exponent = 2;
    }

    if (with_expression && !strisexpr(s)) {
        with_expression = false;
    }
    if (with_expression) {
        if (!amount_parse_expr(&val, s, exponent)) {
            PyMem_Free(s);
            PyErr_SetString(PyExc_ValueError, "couldn't parse expression");
            return NULL;
        }
    } else {
        grouping_sep = amount_parse_grouping_sep(s);
        if (!amount_parse_single(&val, s, exponent, auto_decimal_place, grouping_sep)) {
            PyMem_Free(s);
            PyErr_SetString(PyExc_ValueError, "couldn't parse amount");
            return NULL;
        }
    }
    PyMem_Free(s);
    if ((c == NULL) && (val != 0)) {
        PyErr_SetString(PyExc_ValueError, "No currency given");
        return NULL;
    }

    if (val) {
        return create_amount(val, c);
    } else {
        return PyLong_FromLong(0);
    }
}

static PyObject*
py_amount_convert(PyObject *self, PyObject *args)
{
    PyObject *pyamount;
    char *code;
    PyObject *pydate;
    Amount *amount;
    Amount dest;
    double rate;

    if (!PyArg_ParseTuple(args, "OsO", &pyamount, &code, &pydate)) {
        return NULL;
    }

    amount = get_amount(pyamount);
    if (!amount->val) {
        Py_INCREF(pyamount);
        return pyamount;
    }
    dest.currency = getcur(code);
    if (dest.currency == NULL) {
        return NULL;
    }
    if (dest.currency == amount->currency) {
        Py_INCREF(pyamount);
        return pyamount;
    }
    time_t date = pydate2time(pydate);
    if (date == 1) {
        return NULL;
    }
    if (!amount_convert(&dest, amount, date)) {
        PyErr_SetString(PyExc_ValueError, "problems getting a rate");
        return NULL;
    }
    return create_amount(dest.val, dest.currency);
}

/* Split attrs */
static PyObject *
PySplit_reconciliation_date(PySplit *self)
{
    return time2pydate(self->split.reconciliation_date);
}

static int
PySplit_reconciliation_date_set(PySplit *self, PyObject *value)
{
    time_t res = pydate2time(value);
    if (res == 1) {
        return -1;
    } else {
        self->split.reconciliation_date = res;
        return 0;
    }
}

static PyObject *
PySplit_memo(PySplit *self)
{
    Py_INCREF(self->memo);
    return self->memo;
}

static int
PySplit_memo_set(PySplit *self, PyObject *value)
{
    Py_DECREF(self->memo);
    self->memo = value;
    Py_INCREF(self->memo);
    return 0;
}

static PyObject *
PySplit_reference(PySplit *self)
{
    Py_INCREF(self->reference);
    return self->reference;
}

static int
PySplit_reference_set(PySplit *self, PyObject *value)
{
    Py_DECREF(self->reference);
    self->reference = value;
    Py_INCREF(self->reference);
    return 0;
}

static PyObject *
PySplit_account(PySplit *self)
{
    Py_INCREF(self->account);
    return (PyObject *)self->account;
}

static int
PySplit_account_set(PySplit *self, PyObject *value)
{
    if (value == (PyObject *)self->account) {
        return 0;
    }
    if (value != Py_None) {
        if (!Account_Check(value)) {
            PyErr_SetString(PyExc_ValueError, "not an account");
            return -1;
        }
        PyAccount *account = (PyAccount *)value;
        self->split.account = &account->account;
    } else {
        self->split.account = NULL;
    }
    Py_XDECREF(self->account);
    self->account = (PyAccount *)value;
    Py_INCREF(self->account);

    PySplit_reconciliation_date_set(self, Py_None);
    return 0;
}

static PyObject *
PySplit_amount(PySplit *self)
{
    Split *split = &self->split;
    return create_amount(split->amount.val, split->amount.currency);
}

static int
PySplit_amount_set(PySplit *self, PyObject *value)
{
    Amount *amount;

    amount = get_amount(value);
    if (self->split.amount.currency && amount->currency != self->split.amount.currency) {
        PySplit_reconciliation_date_set(self, Py_None);
    }
    amount_copy(&self->split.amount, amount);
    return 0;
}

static PyObject *
PySplit_account_name(PySplit *self)
{
    if ((PyObject *)self->account == Py_None) {
        return PyUnicode_InternFromString("");
    } else {
        strget(self->account->account.name);
    }
}

static PyObject *
PySplit_credit(PySplit *self)
{
    Amount *a = &self->split.amount;
    if (a->val < 0) {
        return create_amount(-a->val, a->currency);
    } else {
        return PyLong_FromLong(0);
    }
}

static PyObject *
PySplit_debit(PySplit *self)
{
    Amount *a = &self->split.amount;
    if (a->val > 0) {
        return create_amount(a->val, a->currency);
    } else {
        return PyLong_FromLong(0);
    }
}

static PyObject *
PySplit_reconciled(PySplit *self)
{
    if (self->split.reconciliation_date == 0) {
        Py_RETURN_FALSE;
    } else {
        Py_RETURN_TRUE;
    }
}

/* Split Methods */
static int
PySplit_init(PySplit *self, PyObject *args, PyObject *kwds)
{
    PyObject *account, *amount_p;
    Amount *amount;

    static char *kwlist[] = {"account", "amount", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OO", kwlist, &account, &amount_p);
    if (!res) {
        return -1;
    }

    self->account = NULL;
    if (PySplit_account_set(self, account) != 0) {
        return -1;
    }
    amount = get_amount(amount_p);
    amount_copy(&self->split.amount, amount);
    self->memo = PyUnicode_InternFromString("");
    self->split.reconciliation_date = 0;
    self->reference = Py_None;
    Py_INCREF(self->reference);
    return 0;
}

static PyObject *
PySplit_repr(PySplit *self)
{
    PyObject *r, *fmt, *args;

    PyObject *aname = PyObject_GetAttrString((PyObject *)self, "account_name");
    if (aname == NULL) {
        return NULL;
    }
    args = Py_BuildValue(
        "(Ois)", aname, self->split.amount.val,
        self->split.amount.currency->code);
    fmt = PyUnicode_FromString("Split(%r Amount(%r, %r))");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static void
PySplit_dealloc(PySplit *self)
{
    Py_DECREF(self->account);
    Py_DECREF(self->memo);
    Py_DECREF(self->reference);
}

static PyObject *
PySplit_copy_from(PySplit *self, PyObject *args)
{
    PyObject *other;

    if (!PyArg_ParseTuple(args, "O", &other)) {
        return NULL;
    }
    if (!Split_Check(other)) {
        PyErr_SetString(PyExc_TypeError, "not a split");
        return NULL;
    }
    PySplit_account_set(self, (PyObject *)((PySplit *)other)->account);
    amount_copy(&self->split.amount, &((PySplit *)other)->split.amount);
    self->memo = ((PySplit *)other)->memo;
    Py_INCREF(self->memo);
    self->split.reconciliation_date = ((PySplit *)other)->split.reconciliation_date;
    self->reference = ((PySplit *)other)->reference;
    Py_INCREF(self->reference);
    Py_RETURN_NONE;
}

static PyObject *
PySplit_is_on_same_side(PySplit *self, PyObject *args)
{
    PyObject *other;

    if (!PyArg_ParseTuple(args, "O", &other)) {
        return NULL;
    }
    if (!Split_Check(other)) {
        PyErr_SetString(PyExc_TypeError, "not a split");
        return NULL;
    }
    if ((self->split.amount.val > 0) == (((PySplit *)other)->split.amount.val > 0)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PySplit_copy(PySplit *self)
{
    PySplit *r = (PySplit *)PyType_GenericAlloc((PyTypeObject *)Split_Type, 0);
    r->account = NULL;
    PyObject *args = PyTuple_Pack(1, self);
    PySplit_copy_from(r, args);
    Py_DECREF(args);
    return (PyObject *)r;
}

static PyObject *
PySplit_deepcopy(PySplit *self, PyObject *args, PyObject *kwds)
{
    return PySplit_copy(self);
}

/* Entry Methods */
static int
PyEntry_init(PyEntry *self, PyObject *args, PyObject *kwds)
{
    PyObject *amount_p, *balance, *reconciled_balance, *balance_with_budget;
    Amount *amount;

    static char *kwlist[] = {"split", "transaction", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OO", kwlist, &self->split, &self->transaction);
    if (!res) {
        return -1;
    }

    Py_INCREF(self->split);
    Py_INCREF(self->transaction);
    amount_copy(&self->balance, amount_zero());
    amount_copy(&self->reconciled_balance, amount_zero());
    amount_copy(&self->balance_with_budget, amount_zero());
    self->index = -1;
    return 0;
}

static PyObject *
PyEntry_account(PyEntry *self)
{
    return PySplit_account(self->split);
}

static PyObject *
PyEntry_amount(PyEntry *self)
{
    return PySplit_amount(self->split);
}

static PyObject *
PyEntry_balance(PyEntry *self)
{
    return create_amount(self->balance.val, self->balance.currency);
}

static PyObject *
PyEntry_balance_with_budget(PyEntry *self)
{
    return create_amount(self->balance_with_budget.val, self->balance_with_budget.currency);
}

static PyObject *
PyEntry_checkno(PyEntry *self)
{
    return PyObject_GetAttrString(self->transaction, "checkno");
}

static PyObject *
PyEntry_date(PyEntry *self)
{
    return PyObject_GetAttrString(self->transaction, "date");
}

static PyObject *
PyEntry_description(PyEntry *self)
{
    return PyObject_GetAttrString(self->transaction, "description");
}

static PyObject *
PyEntry_index(PyEntry *self)
{
    return PyLong_FromLong(self->index);
}

static PyObject *
PyEntry_payee(PyEntry *self)
{
    return PyObject_GetAttrString(self->transaction, "payee");
}

static PyObject *
PyEntry_mtime(PyEntry *self)
{
    return PyObject_GetAttrString(self->transaction, "mtime");
}

static PyObject *
PyEntry_reconciled(PyEntry *self)
{
    return PySplit_reconciled(self->split);
}

static PyObject *
PyEntry_reconciled_balance(PyEntry *self)
{
    return create_amount(self->reconciled_balance.val, self->reconciled_balance.currency);
}

static PyObject *
PyEntry_reconciliation_date(PyEntry *self)
{
    return PySplit_reconciliation_date(self->split);
}

static PyObject *
_PyEntry_reconciliation_key(PyEntry *self)
{
    PyObject *recdate = PySplit_reconciliation_date(self->split);
    if (recdate == Py_None) {
        Py_DECREF(recdate);
        PyObject *mod = PyImport_ImportModule("datetime");
        if (mod == NULL) {
            return NULL;
        }
        PyObject *tmp = PyObject_GetAttrString(mod, "date");
        Py_DECREF(mod);
        if (tmp == NULL) {
            return NULL;
        }
        recdate = PyObject_GetAttrString(tmp, "min");
        Py_DECREF(tmp);
        if (recdate == NULL) {
            return NULL;
        }
    }
    PyObject *position = PyObject_GetAttrString(self->transaction, "position");
    if (position == NULL) {
        Py_DECREF(recdate);
        return NULL;
    }
    PyObject *date = PyEntry_date(self);
    PyObject *index = PyLong_FromLong(self->index);
    PyObject *tuple = PyTuple_Pack(4, recdate, date, position, index);
    Py_DECREF(recdate);
    Py_DECREF(date);
    Py_DECREF(position);
    Py_DECREF(index);
    return tuple;
}

static PyObject *
PyEntry_reference(PyEntry *self)
{
    return PySplit_reference(self->split);
}

static PyObject *
PyEntry_split(PyEntry *self)
{
    Py_INCREF(self->split);
    return (PyObject *)self->split;
}

static int
PyEntry_split_set(PyEntry *self, PyObject *value)
{
    if (!Split_Check(value)) {
        PyErr_SetString(PyExc_ValueError, "not a split");
        return -1;
    }
    Py_DECREF(self->split);
    self->split = (PySplit *)value;
    Py_INCREF(self->split);
    return 0;
}

static PyObject *
PyEntry_splits(PyEntry *self)
{
    PyObject *tsplits = PyObject_GetAttrString(self->transaction, "splits");
    if (tsplits == NULL) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(tsplits);
    // we assume that self->split is in tsplits, and there only once.
    PyObject *r = PyList_New(len - 1);
    int j = 0;
    for (int i=0; i<len; i++) {
        PyObject *tmp = PyList_GetItem(tsplits, i);
        if (tmp == (PyObject *)self->split) {
            continue;
        }
        Py_INCREF(tmp);
        PyList_SetItem(r, j, tmp);
        j++;
    }
    return r;
}

static PyObject *
PyEntry_transaction(PyEntry *self)
{
    Py_INCREF(self->transaction);
    return self->transaction;
}

static int
PyEntry_transaction_set(PyEntry *self, PyObject *value)
{
    Py_DECREF(self->transaction);
    self->transaction = value;
    Py_INCREF(self->transaction);
    return 0;
}

static PyObject *
PyEntry_transfer(PyEntry *self)
{
    PyObject *splits = PyEntry_splits(self);
    if (splits == NULL) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(splits);
    PyObject *r = PyList_New(0);
    for (int i=0; i<len; i++) {
        PySplit *split = (PySplit *)PyList_GetItem(splits, i); // borrowed
        if ((PyObject *)split->account != Py_None) {
            PyList_Append(r, (PyObject *)split->account);
        }
    }
    return r;
}

/* Change the amount of `split`, from the perspective of the account ledger.
 *
 * This can only be done if the Transaction to which we belong is a two-way
 * transaction. This will trigger a two-way balancing with
 * `Transaction.balance`.
 */
static PyObject*
PyEntry_change_amount(PyEntry *self, PyObject *args)
{
    PyObject *amount_p;

    if (!PyArg_ParseTuple(args, "O", &amount_p)) {
        return NULL;
    }

    PyObject *splits = PyEntry_splits(self);
    if (PyList_Size(splits) != 1) {
        PyErr_SetString(PyExc_ValueError, "not a two-way txn");
        return NULL;
    }
    PySplit *other = (PySplit *)PyList_GetItem(splits, 0); // borrowed
    Py_DECREF(splits);
    PySplit_amount_set(self->split, amount_p);
    Amount *amount = get_amount(amount_p);
    Amount *other_amount = &other->split.amount;
    bool is_mct = false;
    if (!same_currency(amount, other_amount)) {
        bool is_asset = false;
        bool other_is_asset = false;
        PyObject *account = PySplit_account(self->split);
        if (account != Py_None) {
            PyObject *tmp = PyObject_CallMethod(
                account, "is_balance_sheet_account", NULL);
            Py_DECREF(account);
            if (tmp == NULL) {
                return NULL;
            }
            is_asset = PyObject_IsTrue(tmp);
            Py_DECREF(tmp);
        }
        account = PySplit_account(other);
        if (account != Py_None) {
            PyObject *tmp = PyObject_CallMethod(
                account, "is_balance_sheet_account", NULL);
            Py_DECREF(account);
            if (tmp == NULL) {
                return NULL;
            }
            other_is_asset = PyObject_IsTrue(tmp);
            Py_DECREF(tmp);
        }
        if (is_asset && other_is_asset) {
            is_mct = true;
        }
    }

    if (is_mct) {
        // don't touch other side unless we have a logical imbalance
        if ((self->split->split.amount.val > 0) == (other_amount->val > 0)) {
            PyObject *tmp = create_amount(
                other_amount->val * -1, other_amount->currency);
            PySplit_amount_set(other, tmp);
            Py_DECREF(tmp);
        }
    } else {
        PyObject *tmp = create_amount(-amount->val, amount->currency);
        PySplit_amount_set(other, tmp);
        Py_DECREF(tmp);
    }
    Py_RETURN_NONE;
}

static PyObject*
PyEntry_normal_balance(PyEntry *self, PyObject *args)
{
    Amount amount;
    amount_copy(&amount, &self->balance);
    PyObject *account = PySplit_account(self->split);
    if (account != Py_None) {
        PyObject *tmp = PyObject_CallMethod(account, "is_credit_account", NULL);
        Py_DECREF(account);
        if (tmp == NULL) {
            return NULL;
        }
        if (PyObject_IsTrue(tmp)) {
            amount.val *= -1;
        }
        Py_DECREF(tmp);
    }
    return create_amount(amount.val, amount.currency);
}

static PyObject *
PyEntry_copy(PyEntry *self)
{
    PyEntry *r = (PyEntry *)PyType_GenericAlloc((PyTypeObject *)Entry_Type, 0);
    r->split = self->split;
    Py_INCREF(r->split);
    r->transaction = self->transaction;
    Py_INCREF(r->transaction);
    amount_copy(&r->balance, &self->balance);
    amount_copy(&r->reconciled_balance, &self->reconciled_balance);
    amount_copy(&r->balance_with_budget, &self->balance_with_budget);
    r->index = self->index;
    return (PyObject *)r;
}

static PyObject *
PyEntry_deepcopy(PyEntry *self, PyObject *args, PyObject *kwds)
{
    return PyEntry_copy(self);
}

static PyObject *
PyEntry_richcompare(PyEntry *a, PyObject *b, int op)
{
    if (!Entry_Check(b)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if (op == Py_EQ) {
        if (a->split == ((PyEntry *)b)->split) {
            Py_RETURN_TRUE;
        } else {
            Py_RETURN_FALSE;
        }
    } else if (op == Py_LT) {
        PyObject *d1 = PyEntry_date(a);
        PyObject *d2 = PyEntry_date((PyEntry *)b);
        PyObject *res = PyObject_RichCompare(d1, d2, op);
        Py_DECREF(d1);
        Py_DECREF(d2);
        return res;
    } else {
        Py_RETURN_NOTIMPLEMENTED;
    }
}

static Py_hash_t
PyEntry_hash(PyEntry *self)
{
    return PyObject_Hash((PyObject *)self->split);
}

static PyObject *
PyEntry_repr(PyEntry *self)
{
    PyObject *r, *fmt, *args;

    PyObject *tdate = PyObject_GetAttrString(self->transaction, "date");
    if (tdate == NULL) {
        return NULL;
    }
    PyObject *tdesc = PyObject_GetAttrString(self->transaction, "description");
    if (tdesc == NULL) {
        Py_DECREF(tdate);
        return NULL;
    }
    args = Py_BuildValue("(OO)", tdate, tdesc);
    Py_DECREF(tdate);
    Py_DECREF(tdesc);
    fmt = PyUnicode_FromString("Entry(%s %s))");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static void
PyEntry_dealloc(PyEntry *self)
{
    Py_DECREF(self->split);
    Py_DECREF(self->transaction);
}

/* EntryList */
static int
PyEntryList_init(PyEntryList *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist)) {
        return -1;
    }
    self->entries = PyList_New(0);
    self->last_reconciled = NULL;
    return 0;
}

static void
_PyEntryList_maybe_set_last_reconciled(PyEntryList *self, PyEntry *entry)
{
    // we don't bother increfing last_reconciled: implicit in entries'
    // membership
    if (entry->split->split.reconciliation_date != 0) {
        if (self->last_reconciled == NULL) {
            self->last_reconciled = entry;
        } else {
            PyObject *key1 = _PyEntry_reconciliation_key(self->last_reconciled);
            PyObject *key2 = _PyEntry_reconciliation_key(entry);
            if (PyObject_RichCompareBool(key2, key1, Py_GE) > 0) {
                self->last_reconciled = entry;
            }
            Py_DECREF(key1);
            Py_DECREF(key2);
        }
    }
}

static void
_PyEntryList_add_entry(PyEntryList *self, PyEntry *entry)
{
    PyList_Append(self->entries, (PyObject *)entry);
    _PyEntryList_maybe_set_last_reconciled(self, entry);
}

static int
_PyEntryList_find_date(PyEntryList *self, PyObject *date, bool equal)
{
    // equal=true: find index with closest smaller-or-equal date to "date"
    // equal=false: find smaller only
    // Returns the index *following* the nearest result. Returned index goes
    // over the threshold.
    int opid = equal ? Py_GT : Py_GE;
    Py_ssize_t len = PyList_Size(self->entries);
    if (len == 0) {
        return 0;
    }
    Py_ssize_t low = 0;
    Py_ssize_t high = len - 1;
    bool matched_once = false;
    while ((high > low) || ((high == low) && !matched_once)) {
        Py_ssize_t mid = ((high - low) / 2) + low;
        PyEntry *entry = (PyEntry *)PyList_GetItem(self->entries, mid); // borrowed
        PyObject *tdate = PyEntry_date(entry);
        int cmp = PyObject_RichCompareBool(tdate, date, opid);
        Py_DECREF(tdate);
        if (cmp > 0) {
            matched_once = true;
            high = mid;
        } else {
            low = mid + 1;
        }
    }
    if (matched_once) {
        // we have at least one entry with a higher date than "date"
        return (int)high;
    } else {
        // All entries have a smaller date than "date". Return len.
        return len;
    }

}

static PyObject*
PyEntryList_last_entry(PyEntryList *self, PyObject *args)
{
    PyObject *date = NULL;

    if (!PyArg_ParseTuple(args, "|O", &date)) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(self->entries);
    if (!len) {
        Py_RETURN_NONE;
    }
    int index;
    if (date == Py_None) {
        index = len;
    } else {
        index = _PyEntryList_find_date(self, date, true);
    }
    // We want the entry *before* the threshold
    index--;
    PyObject *res;
    if (index >= 0) {
        res = PyList_GetItem(self->entries, index);
        if (res == NULL) {
            return NULL;
        }
    } else {
        res = Py_None;
    }
    Py_INCREF(res);
    return res;
}

static PyObject*
PyEntryList_clear(PyEntryList *self, PyObject *args)
{
    PyObject *date;

    if (!PyArg_ParseTuple(args, "O", &date)) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(self->entries);
    int index;
    if (date == Py_None) {
        index = 0;
    } else {
        index = _PyEntryList_find_date(self, date, false);
        if (index >= len) {
            // Everything is smaller, don't clear anything.
            Py_RETURN_NONE;
        }
    }
    if (PyList_SetSlice(self->entries, index, len, NULL) == -1) {
        return NULL;
    }
    self->last_reconciled = NULL;
    for (int i=0; i<index; i++) {
        _PyEntryList_maybe_set_last_reconciled(
            self, (PyEntry *)PyList_GetItem(self->entries, i));
    }
    Py_RETURN_NONE;
}

static bool
_PyEntryList_balance(
    PyEntryList *self, Amount *dst, PyObject *date_p, bool with_budget)
{
    Py_ssize_t len = PyList_Size(self->entries);
    if (!len) {
        dst->val = 0;
        return true;
    }
    int index;
    if (date_p == Py_None) {
        index = len;
    } else {
        index = _PyEntryList_find_date(self, date_p, true);
    }
    // We want the entry *before* the threshold
    index--;
    if (index >= 0) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(self->entries, index); // borrowed
        if (entry == NULL) {
            return false;
        }
        Amount *src = with_budget ? &entry->balance_with_budget : &entry->balance;
        if (date_p != Py_None) {
            time_t date = pydate2time(date_p);
            if (date == 1) {
                return NULL;
            }
            if (amount_convert(dst, src, date)) {
                return true;
            } else {
                return false;
            }
        } else {
            amount_copy(dst, src);
            return true;
        }
    } else {
        dst->val = 0;
        return true;
    }
}

static PyObject*
PyEntryList_balance(PyEntryList *self, PyObject *args)
{
    PyObject *date_p;
    char *currency;
    int with_budget = false;

    if (!PyArg_ParseTuple(args, "Os|p", &date_p, &currency, &with_budget)) {
        return NULL;
    }

    Amount dst;
    dst.currency = getcur(currency);
    if (dst.currency == NULL) {
        return NULL;
    }
    if (!_PyEntryList_balance(self, &dst, date_p, with_budget)) {
        return NULL;
    } else {
        if (dst.currency != NULL) {
            return create_amount(dst.val, dst.currency);
        } else {
            return PyLong_FromLong(0);
        }
    }
}

static bool
_PyEntryList_balance_of_reconciled(PyEntryList *self, Amount *dst)
{
    if (self->last_reconciled == NULL) {
        dst->val = 0;
        return false;
    } else {
        amount_copy(dst, &self->last_reconciled->reconciled_balance);
        return true;
    }
}

static PyObject*
PyEntryList_balance_of_reconciled(PyEntryList *self, PyObject *args)
{
    Amount amount;
    if (_PyEntryList_balance_of_reconciled(self, &amount)) {
        return create_amount(amount.val, amount.currency);
    } else {
        return PyLong_FromLong(0);
    }
}

static bool
_PyEntryList_cash_flow(PyEntryList *self, Amount *dst, PyObject *daterange)
{
    dst->val = 0;
    Py_ssize_t len = PyList_Size(self->entries);
    for (int i=0; i<len; i++) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(self->entries, i); // borrowed
        PyObject *tmp = PyObject_GetAttrString(entry->transaction, "TYPE");
        if (tmp == NULL) {
            return false;
        }
        int txn_type = PyLong_AsLong(tmp);
        Py_DECREF(tmp);
        if (txn_type == TXN_TYPE_BUDGET) {
            continue;
        }
        PyObject *date_p = PyEntry_date(entry);
        if (date_p == NULL) {
            return false;
        }
        if (PySequence_Contains(daterange, date_p)) {
            Amount a;
            a.currency = dst->currency;
            Amount *src = &entry->split->split.amount;
            time_t date = pydate2time(date_p);
            if (date == 1) {
                return false;
            }
            if (!amount_convert(&a, src, date)) {
                return false;
            }
            dst->val += a.val;
        }
        Py_DECREF(date_p);
    }
    return true;
}

static PyObject*
PyEntryList_cash_flow(PyEntryList *self, PyObject *args)
{
    PyObject *daterange;
    char *currency;

    if (!PyArg_ParseTuple(args, "Os", &daterange, &currency)) {
        return NULL;
    }
    Amount res;
    res.currency = getcur(currency);
    if (res.currency == NULL) {
        return NULL;
    }
    if (!_PyEntryList_cash_flow(self, &res, daterange)) {
        return NULL;
    }
    return create_amount(res.val, res.currency);
}

static PyObject*
PyEntryList_iter(PyEntryList *self)
{
    return PyObject_GetIter(self->entries);
}

static Py_ssize_t
PyEntryList_len(PyEntryList *self)
{
    return PyList_Size(self->entries);
}

static void
PyEntryList_dealloc(PyEntryList *self)
{
    Py_DECREF(self->entries);
}

/* Account */
static PyObject *
PyAccount_name(PyAccount *self)
{
    return strget(self->account.name);
}

static int
PyAccount_name_set(PyAccount *self, PyObject *value)
{
    return strset(&self->account.name, value) ? 0 : -1;
}

static PyObject *
PyAccount_currency(PyAccount *self)
{
    int len;
    len = strlen(self->account.currency->code);
    return PyUnicode_DecodeASCII(self->account.currency->code, len, NULL);
}

static int
PyAccount_currency_set(PyAccount *self, PyObject *value)
{
    PyObject *tmp = PyUnicode_AsASCIIString(value);
    if (tmp == NULL) {
        return -1;
    }
    Currency *cur = getcur(PyBytes_AsString(tmp));
    Py_DECREF(tmp);
    if (cur == NULL) {
        return -1;
    }
    self->account.currency = cur;
    return 0;
}

static PyObject *
PyAccount_type(PyAccount *self)
{
    char *s;
    switch (self->account.type) {
        case ACCOUNT_ASSET: s = "asset"; break;
        case ACCOUNT_LIABILITY: s = "liability"; break;
        case ACCOUNT_INCOME: s = "income"; break;
        case ACCOUNT_EXPENSE: s = "expense"; break;
    }
    return PyUnicode_InternFromString(s);
}

static int
PyAccount_type_set(PyAccount *self, PyObject *value)
{
    PyObject *tmp = PyUnicode_AsASCIIString(value);
    if (tmp == NULL) {
        return -1;
    }
    char *s = PyBytes_AsString(tmp);
    if (strcmp(s, "asset") == 0) {
        self->account.type = ACCOUNT_ASSET;
    } else if (strcmp(s, "liability") == 0) {
        self->account.type = ACCOUNT_LIABILITY;
    } else if (strcmp(s, "income") == 0) {
        self->account.type = ACCOUNT_INCOME;
    } else if (strcmp(s, "expense") == 0) {
        self->account.type = ACCOUNT_EXPENSE;
    } else {
        PyErr_SetString(PyExc_ValueError, "invalid type");
        return -1;
    }
    return 0;
}

static PyObject *
PyAccount_reference(PyAccount *self)
{
    return strget(self->account.reference);
}

static int
PyAccount_reference_set(PyAccount *self, PyObject *value)
{
    return strset(&self->account.reference, value) ? 0 : -1;
}

static PyObject *
PyAccount_groupname(PyAccount *self)
{
    return strget(self->account.groupname);
}

static int
PyAccount_groupname_set(PyAccount *self, PyObject *value)
{
    return strset(&self->account.groupname, value) ? 0 : -1;
}

static PyObject *
PyAccount_account_number(PyAccount *self)
{
    return strget(self->account.account_number);
}

static int
PyAccount_account_number_set(PyAccount *self, PyObject *value)
{
    return strset(&self->account.account_number, value) ? 0 : -1;
}

static PyObject *
PyAccount_inactive(PyAccount *self)
{
    if (self->account.inactive) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static int
PyAccount_inactive_set(PyAccount *self, PyObject *value)
{
    self->account.inactive = PyObject_IsTrue(value);
    return 0;
}

static PyObject *
PyAccount_notes(PyAccount *self)
{
    return strget(self->account.notes);
}

static int
PyAccount_notes_set(PyAccount *self, PyObject *value)
{
    return strset(&self->account.notes, value) ? 0 : -1;
}

static PyObject *
PyAccount_entries(PyAccount *self)
{
    Py_INCREF(self->entries);
    return (PyObject *)self->entries;
}

static int
PyAccount_init(PyAccount *self, PyObject *args, PyObject *kwds)
{
    PyObject *name, *currency, *type;

    static char *kwlist[] = {"name", "currency", "type", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OOO", kwlist, &name, &currency, &type);
    if (!res) {
        return -1;
    }

    if (PyAccount_currency_set(self, currency) < 0) {
        return -1;
    }
    if (PyAccount_type_set(self, type) < 0) {
        return -1;
    }
    Account *a = &self->account;
    a->name = NULL;
    if (!strset(&a->name, name)) {
        return -1;
    }
    a->id = account_newid();
    a->inactive = false;
    a->reference = NULL;
    a->account_number = "";
    a->notes = "";
    a->groupname = NULL;
    self->entries = PyType_GenericAlloc((PyTypeObject *)EntryList_Type, 0);
    ((PyEntryList *)self->entries)->entries = PyList_New(0);
    ((PyEntryList *)self->entries)->last_reconciled = NULL;
    return 0;
}

static PyObject *
PyAccount_repr(PyAccount *self)
{
    return PyUnicode_FromFormat("Account(%s)", self->account.name);
}

static Py_hash_t
PyAccount_hash(PyAccount *self)
{
    return self->account.id;
}

static PyObject*
PyAccount_normalize_amount(PyAccount *self, PyObject *amount)
{
    if (!check_amount(amount)) {
        PyErr_SetString(PyExc_ValueError, "not an amount");
        return NULL;
    }
    Amount res;
    amount_copy(&res, &((PyAmount *)amount)->amount);
    account_normalize_amount(&self->account, &res);
    return create_amount(res.val, res.currency);
}

static PyObject*
PyAccount_normal_balance(PyAccount *self, PyObject *args)
{
    PyObject *date = Py_None;
    char *currency = NULL;

    if (!PyArg_ParseTuple(args, "|Os", &date, &currency)) {
        return NULL;
    }
    Amount res;
    if (currency == NULL) {
        res.currency = self->account.currency;
    } else {
        res.currency = getcur(currency);
        if (res.currency == NULL) {
            return NULL;
        }
    }
    if (!_PyEntryList_balance((PyEntryList *)self->entries, &res, date, false)) {
        return NULL;
    } else {
        account_normalize_amount(&self->account, &res);
        return create_amount(res.val, res.currency);
    }
}

static PyObject*
PyAccount_normal_balance_of_reconciled(PyAccount *self, PyObject *args)
{
    Amount res;
    if (!_PyEntryList_balance_of_reconciled((PyEntryList *)self->entries, &res)) {
        return NULL;
    } else {
        account_normalize_amount(&self->account, &res);
        return create_amount(res.val, res.currency);
    }
}

static PyObject*
PyAccount_normal_cash_flow(PyAccount *self, PyObject *args)
{
    PyObject *daterange;
    char *currency = NULL;

    if (!PyArg_ParseTuple(args, "O|s", &daterange, &currency)) {
        return NULL;
    }
    Amount res;
    if (currency == NULL) {
        res.currency = self->account.currency;
    } else {
        res.currency = getcur(currency);
        if (res.currency == NULL) {
            return NULL;
        }
    }
    if (!_PyEntryList_cash_flow((PyEntryList *)self->entries, &res, daterange)) {
        return NULL;
    } else {
        account_normalize_amount(&self->account, &res);
        return create_amount(res.val, res.currency);
    }
}

static PyObject*
PyAccount_is_balance_sheet_account(PyAccount *self, PyObject *args)
{
    if (account_is_balance_sheet(&self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_credit_account(PyAccount *self, PyObject *args)
{
    if (account_is_credit(&self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_debit_account(PyAccount *self, PyObject *args)
{
    if (account_is_debit(&self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_income_statement_account(PyAccount *self, PyObject *args)
{
    if (account_is_income_statement(&self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_combined_display(PyAccount *self)
{
    if (self->account.account_number[0] != '\0') {
        return PyUnicode_FromFormat(
            "%s - %s", self->account.account_number, self->account.name);
    } else {
        return PyAccount_name(self);
    }
}

static PyObject *
PyAccount_copy(PyAccount *self)
{
    PyAccount *r = (PyAccount *)PyType_GenericAlloc((PyTypeObject *)Account_Type, 0);
    Account *a = &self->account;
    Account *c = &r->account;
    c->type = a->type;
    c->currency = a->currency;
    c->name = NULL;
    if (!strclone(&c->name, a->name)) {
        return NULL;
    }
    c->id = a->id;
    c->inactive = a->inactive;
    c->reference = NULL;
    if (!strclone(&c->reference, a->reference)) {
        return NULL;
    }
    c->account_number = NULL;
    if (!strclone(&c->account_number, a->account_number)) {
        return NULL;
    }
    c->notes = NULL;
    if (!strclone(&c->notes, a->notes)) {
        return NULL;
    }
    c->groupname = NULL;
    if (!strclone(&c->groupname, a->groupname)) {
        return NULL;
    }
    // We don't deep copy entries. not needed.
    r->entries = PyType_GenericAlloc((PyTypeObject *)EntryList_Type, 0);
    ((PyEntryList *)r->entries)->entries = PySequence_List(((PyEntryList *)self->entries)->entries);
    ((PyEntryList *)r->entries)->last_reconciled = ((PyEntryList *)self->entries)->last_reconciled;
    return (PyObject *)r;
}

static PyObject *
PyAccount_deepcopy(PyAccount *self, PyObject *args, PyObject *kwds)
{
    return PyAccount_copy(self);
}

static void
PyAccount_dealloc(PyAccount *self)
{
    Account *a = &self->account;
    strfree(&a->name);
    strfree(&a->reference);
    strfree(&a->groupname);
    strfree(&a->account_number);
    strfree(&a->notes);
    Py_DECREF(self->entries);
}

/* Oven functions */

static bool
_py_oven_cook_splits(PyObject *splitpairs, PyAccount *account)
{
    Amount amount;
    Amount balance;
    Amount balance_with_budget;
    Amount reconciled_balance;

    balance.currency = account->account.currency;
    balance_with_budget.currency = balance.currency;
    reconciled_balance.currency = balance.currency;
    amount.currency = balance.currency;

    PyEntryList *entries = (PyEntryList *)account->entries;
    if (!_PyEntryList_balance(entries, &balance, Py_None, false)) {
        return false;
    }
    if (!_PyEntryList_balance(entries, &balance_with_budget, Py_None, true)) {
        return false;
    }
    _PyEntryList_balance_of_reconciled(entries, &reconciled_balance);
    Py_ssize_t len = PySequence_Length(splitpairs);
    PyObject *res = PyList_New(len);
    // Entry tuples for reconciliation order
    PyObject *rentries = PyList_New(len);
    for (int i=0; i<len; i++) {
        PyObject *item = PySequence_GetItem(splitpairs, i);
        PyEntry *entry = (PyEntry *)PyType_GenericAlloc((PyTypeObject *)Entry_Type, 0);
        entry->transaction = PyTuple_GetItem(item, 0); // borrowed
        if (entry->transaction == NULL) {
            Py_DECREF(item);
            Py_DECREF(entry);
            Py_DECREF(res);
            return false;
        }
        entry->split = (PySplit *)PyTuple_GetItem(item, 1); // borrowed
        if (entry->split == NULL) {
            Py_DECREF(item);
            Py_DECREF(entry);
            Py_DECREF(res);
            return NULL;
        }
        Py_INCREF(entry->split);
        Py_INCREF(entry->transaction);
        entry->index = i;
        PyObject *tmp = PyObject_GetAttrString(entry->transaction, "TYPE");
        if (tmp == NULL) {
            return false;
        }
        int txn_type = PyLong_AsLong(tmp);
        Py_DECREF(tmp);
        tmp = PyEntry_date(entry);
        if (tmp == NULL) {
            return false;
        }
        time_t date = pydate2time(tmp);
        if (date == 1) {
            return false;
        }
        Py_DECREF(tmp);

        Split *split = &entry->split->split;
        if (!amount_convert(&amount, &split->amount, date)) {
            return false;
        }
        if (txn_type != TXN_TYPE_BUDGET) {
            balance.val += amount.val;
        }
        amount_copy(&entry->balance, &balance);
        balance_with_budget.val += amount.val;
        amount_copy(&entry->balance_with_budget, &balance_with_budget);

        PyObject *rdate = PySplit_reconciliation_date(entry->split);
        PyObject *tdate = PyObject_GetAttrString(entry->transaction, "date");
        if (rdate == Py_None) {
            rdate = tdate;
            Py_INCREF(rdate);
        }
        PyObject *tpos = PyObject_GetAttrString(entry->transaction, "position");
        PyObject *tuple = PyTuple_Pack(4, rdate, tdate, tpos, entry);
        Py_DECREF(rdate);
        Py_DECREF(tdate);
        Py_DECREF(tpos);
        PyList_SetItem(res, i, (PyObject *)entry); // stolen
        PyList_SetItem(rentries, i, tuple); // stolen
    }

    if (PyList_Sort(rentries) == -1) {
        Py_DECREF(rentries);
        Py_DECREF(res);
        return false;
    }
    for (int i=0; i<len; i++) {
        PyObject *tuple = PyList_GetItem(rentries, i); // borrowed
        PyEntry *entry = (PyEntry *)PyTuple_GetItem(tuple, 3); // borrowed
        if (entry->split->split.reconciliation_date != 0) {
            reconciled_balance.val += entry->split->split.amount.val;
        }
        amount_copy(&entry->reconciled_balance, &reconciled_balance);
    }
    Py_DECREF(rentries);
    for (int i=0; i<len; i++) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(res, i); // borrowed
        _PyEntryList_add_entry(entries, entry);
    }
    Py_DECREF(res);
    return true;
}

/* "Cook" txns into Entry with running balances
 *
 * This takes a list of transactions to cook. Adds entries directly in the
 * proper accounts.
 */
static PyObject*
py_oven_cook_txns(PyObject *self, PyObject *txns)
{
    Py_ssize_t len = PySequence_Length(txns);
    PyObject *a2s = PyDict_New();
    for (int i=0; i<len; i++) {
        PyObject *txn = PyList_GetItem(txns, i); // borrowed
        PyObject *splits = PyObject_GetAttrString(txn, "splits");
        if (splits == NULL) {
            return NULL;
        }
        Py_ssize_t slen = PySequence_Length(splits);
        for (int j=0; j<slen; j++) {
            PySplit *split = (PySplit *)PyList_GetItem(splits, j); // borrowed
            if ((PyObject *)split->account == Py_None) {
                continue;
            }
            PyObject *splitpairs = PyDict_GetItem(a2s, (PyObject *)split->account);
            if (splitpairs == NULL) {
                splitpairs = PyList_New(0);
                PyDict_SetItem(a2s, (PyObject *)split->account, splitpairs);
                Py_DECREF(splitpairs);
            }
            PyObject *pair = PyTuple_Pack(2, txn, split);
            PyList_Append(splitpairs, pair);
            Py_DECREF(pair);
        }
    }

    Py_ssize_t pos = 0;
    PyObject *k, *v;
    while (PyDict_Next(a2s, &pos, &k, &v)) {
        if (!_py_oven_cook_splits(v, (PyAccount *)k)) {
            return NULL;
        }
    }
    Py_RETURN_NONE;
}

/* Python Boilerplate */

/* We need both __copy__ and __deepcopy__ methods for amounts to behave
 * correctly in undo_test. */
static PyMethodDef PyAmount_methods[] = {
    {"__copy__", (PyCFunction)PyAmount_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PyAmount_deepcopy, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyAmount_getseters[] = {
    {"currency_code", (getter)PyAmount_getcurrency_code, NULL, "currency_code", NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Amount_Slots[] = {
    {Py_tp_init, PyAmount_init},
    {Py_tp_repr, PyAmount_repr},
    {Py_tp_hash, PyAmount_hash},
    {Py_tp_richcompare, PyAmount_richcompare},
    {Py_tp_methods, PyAmount_methods},
    {Py_tp_getset, PyAmount_getseters},
    {Py_nb_add, PyAmount_add},
    {Py_nb_subtract, PyAmount_sub},
    {Py_nb_multiply, PyAmount_mul},
    {Py_nb_negative, PyAmount_neg},
    {Py_nb_absolute, PyAmount_abs},
    {Py_nb_bool, PyAmount_bool},
    {Py_nb_float, PyAmount_float},
    {Py_nb_true_divide, PyAmount_true_divide},
    {0, 0},
};

PyType_Spec Amount_Type_Spec = {
    "_ccore.Amount",
    sizeof(PyAmount),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Amount_Slots,
};

static PyMethodDef PySplit_methods[] = {
    {"__copy__", (PyCFunction)PySplit_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PySplit_deepcopy, METH_VARARGS, ""},
    {"copy_from", (PyCFunction)PySplit_copy_from, METH_VARARGS, ""},
    {"is_on_same_side", (PyCFunction)PySplit_is_on_same_side, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PySplit_getseters[] = {
    /* Account our split is assigned to.
     * Can be `None`. We are then considered an "unassigned split".
     * Setting this resets `reconciliation_date` to `None`.
     */
    {"account", (getter)PySplit_account, (setter)PySplit_account_set, "account", NULL},

    /* Amount by which we affect our `account`.
     * - A value higher than 0 makes this a "debit split".
     * - A value lower than 0 makes this a "credit split".
     * - A value of 0 makes this a "null split".
     * Setting this resets `reconciliation_date` to `None`.
     */
    {"amount", (getter)PySplit_amount, (setter)PySplit_amount_set, "amount", NULL},
    {"reconciliation_date", (getter)PySplit_reconciliation_date, (setter)PySplit_reconciliation_date_set, "reconciliation_date", NULL},
    {"memo", (getter)PySplit_memo, (setter)PySplit_memo_set, "memo", NULL},
    {"reference", (getter)PySplit_reference, (setter)PySplit_reference_set, "reference", NULL},

    // Name for `account` or an empty string if `None`.
    {"account_name", (getter)PySplit_account_name, NULL, "account_name", NULL},

    // Returns `amount` (reverted so it's positive) if < 0. Otherwise, 0.
    {"credit", (getter)PySplit_credit, NULL, "credit", NULL},

    // Returns `amount` if > 0. Otherwise, 0.
    {"debit", (getter)PySplit_debit, NULL, "debit", NULL},

    // bool. Whether `reconciliation_date` is set to something.
    {"reconciled", (getter)PySplit_reconciled, NULL, "reconciled", NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Split_Slots[] = {
    {Py_tp_init, PySplit_init},
    {Py_tp_methods, PySplit_methods},
    {Py_tp_getset, PySplit_getseters},
    {Py_tp_repr, PySplit_repr},
    {Py_tp_dealloc, PySplit_dealloc},
    {0, 0},
};

PyType_Spec Split_Type_Spec = {
    "_ccore.Split",
    sizeof(PySplit),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Split_Slots,
};

static PyMethodDef PyEntry_methods[] = {
    {"__copy__", (PyCFunction)PyEntry_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PyEntry_deepcopy, METH_VARARGS, ""},
    {"change_amount", (PyCFunction)PyEntry_change_amount, METH_VARARGS, ""},
    {"normal_balance", (PyCFunction)PyEntry_normal_balance, METH_NOARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyEntry_getseters[] = {
    {"account", (getter)PyEntry_account, NULL, NULL, NULL},
    {"amount", (getter)PyEntry_amount, NULL, NULL, NULL},
    {"balance", (getter)PyEntry_balance, NULL, NULL, NULL},
    {"balance_with_budget", (getter)PyEntry_balance_with_budget, NULL, NULL, NULL},
    {"checkno", (getter)PyEntry_checkno, NULL, NULL, NULL},
    {"date", (getter)PyEntry_date, NULL, NULL, NULL},
    {"description", (getter)PyEntry_description, NULL, NULL, NULL},
    {"mtime", (getter)PyEntry_mtime, NULL, NULL, NULL},
    {"payee", (getter)PyEntry_payee, NULL, NULL, NULL},
    {"reconciled", (getter)PyEntry_reconciled, NULL, NULL, NULL},
    {"reconciled_balance", (getter)PyEntry_reconciled_balance, NULL, NULL, NULL},
    {"reconciliation_date", (getter)PyEntry_reconciliation_date, NULL, NULL, NULL},
    {"reference", (getter)PyEntry_reference, NULL, NULL, NULL},
    {"split", (getter)PyEntry_split, (setter)PyEntry_split_set, NULL, NULL},
    {"splits", (getter)PyEntry_splits, NULL, NULL, NULL},
    {"transaction", (getter)PyEntry_transaction, (setter)PyEntry_transaction_set, NULL, NULL},
    {"transfer", (getter)PyEntry_transfer, NULL, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Entry_Slots[] = {
    {Py_tp_init, PyEntry_init},
    {Py_tp_methods, PyEntry_methods},
    {Py_tp_getset, PyEntry_getseters},
    {Py_tp_repr, PyEntry_repr},
    {Py_tp_richcompare, PyEntry_richcompare},
    {Py_tp_hash, PyEntry_hash},
    {Py_tp_dealloc, PyEntry_dealloc},
    {0, 0},
};

PyType_Spec Entry_Type_Spec = {
    "_ccore.Entry",
    sizeof(PyEntry),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Entry_Slots,
};

static PyMethodDef module_methods[] = {
    {"amount_format", (PyCFunction)py_amount_format, METH_VARARGS | METH_KEYWORDS},
    {"amount_parse", (PyCFunction)py_amount_parse, METH_VARARGS | METH_KEYWORDS},
    {"amount_convert", (PyCFunction)py_amount_convert, METH_VARARGS},
    {"currency_global_init", py_currency_global_init, METH_VARARGS},
    {"currency_global_reset_currencies", py_currency_global_reset_currencies, METH_NOARGS},
    {"currency_register", py_currency_register, METH_VARARGS},
    {"currency_getrate", py_currency_getrate, METH_VARARGS},
    {"currency_set_CAD_value", py_currency_set_CAD_value, METH_VARARGS},
    {"currency_daterange", py_currency_daterange, METH_VARARGS},
    {"oven_cook_txns", py_oven_cook_txns, METH_O},
    {NULL}  /* Sentinel */
};

static PyMethodDef PyEntryList_methods[] = {
    // Returns running balance at `date`.
    // If `currency` is specified, the result is converted to it.
    // if `with_budget` is True, budget spawns are counted.
    {"balance", (PyCFunction)PyEntryList_balance, METH_VARARGS, ""},
    // Returns `reconciled_balance` for our last reconciled entry.
    {"balance_of_reconciled", (PyCFunction)PyEntryList_balance_of_reconciled, METH_NOARGS, ""},
    // Returns the sum of entry amounts occuring in `date_range`.
    // If `currency` is specified, the result is converted to it.
    {"cash_flow", (PyCFunction)PyEntryList_cash_flow, METH_VARARGS, ""},
    // Remove all entries after `from_date`.
    {"clear", (PyCFunction)PyEntryList_clear, METH_VARARGS, ""},
    // Return the last entry with a date that isn't after `date`.
    // If `date` isn't specified, returns the last entry in the list.
    {"last_entry", (PyCFunction)PyEntryList_last_entry, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyType_Slot EntryList_Slots[] = {
    {Py_tp_init, PyEntryList_init},
    {Py_tp_methods, PyEntryList_methods},
    {Py_sq_length, PyEntryList_len},
    {Py_tp_iter, PyEntryList_iter},
    {Py_tp_dealloc, PyEntryList_dealloc},
    {0, 0},
};

PyType_Spec EntryList_Type_Spec = {
    "_ccore.EntryList",
    sizeof(PyEntryList),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    EntryList_Slots,
};

static PyMethodDef PyAccount_methods[] = {
    {"__copy__", (PyCFunction)PyAccount_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PyAccount_deepcopy, METH_VARARGS, ""},
    {"normalize_amount", (PyCFunction)PyAccount_normalize_amount, METH_O, ""},
    {"normal_balance", (PyCFunction)PyAccount_normal_balance, METH_VARARGS, ""},
    {"normal_balance_of_reconciled", (PyCFunction)PyAccount_normal_balance_of_reconciled, METH_NOARGS, ""},
    {"normal_cash_flow", (PyCFunction)PyAccount_normal_cash_flow, METH_VARARGS, ""},
    {"is_balance_sheet_account", (PyCFunction)PyAccount_is_balance_sheet_account, METH_NOARGS, ""},
    {"is_credit_account", (PyCFunction)PyAccount_is_credit_account, METH_NOARGS, ""},
    {"is_debit_account", (PyCFunction)PyAccount_is_debit_account, METH_NOARGS, ""},
    {"is_income_statement_account", (PyCFunction)PyAccount_is_income_statement_account, METH_NOARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyAccount_getseters[] = {
    {"combined_display", (getter)PyAccount_combined_display, NULL, NULL, NULL},
    {"currency", (getter)PyAccount_currency, (setter)PyAccount_currency_set, NULL, NULL},
    {"type", (getter)PyAccount_type, (setter)PyAccount_type_set, NULL, NULL},
    {"name", (getter)PyAccount_name, (setter)PyAccount_name_set, NULL, NULL},
    {"reference", (getter)PyAccount_reference, (setter)PyAccount_reference_set, NULL, NULL},
    {"groupname", (getter)PyAccount_groupname, (setter)PyAccount_groupname_set, NULL, NULL},
    {"account_number", (getter)PyAccount_account_number, (setter)PyAccount_account_number_set, NULL, NULL},
    {"inactive", (getter)PyAccount_inactive, (setter)PyAccount_inactive_set, NULL, NULL},
    {"notes", (getter)PyAccount_notes, (setter)PyAccount_notes_set, NULL, NULL},
    {"entries", (getter)PyAccount_entries, NULL, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Account_Slots[] = {
    {Py_tp_init, PyAccount_init},
    {Py_tp_methods, PyAccount_methods},
    {Py_tp_getset, PyAccount_getseters},
    {Py_tp_hash, PyAccount_hash},
    {Py_tp_repr, PyAccount_repr},
    {Py_tp_dealloc, PyAccount_dealloc},
    {0, 0},
};

PyType_Spec Account_Type_Spec = {
    "_ccore.Account",
    sizeof(PyAccount),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Account_Slots,
};

static struct PyModuleDef CCoreDef = {
    PyModuleDef_HEAD_INIT,
    "_ccore",
    NULL,
    -1,
    module_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyObject *
PyInit__ccore(void)
{
    PyObject *m;

    m = PyModule_Create(&CCoreDef);
    if (m == NULL) {
        return NULL;
    }

    PyDateTime_IMPORT;
    Amount_Type = PyType_FromSpec(&Amount_Type_Spec);
    PyModule_AddObject(m, "Amount", Amount_Type);

    UnsupportedCurrencyError = PyErr_NewExceptionWithDoc(
        "_ccore.UnsupportedCurrencyError",
        "We're trying to parse an amount specifying an unsupported currency.",
        PyExc_ValueError,
        NULL);

    if (UnsupportedCurrencyError == NULL) {
        return NULL;
    }

    PyModule_AddObject(m, "UnsupportedCurrencyError", UnsupportedCurrencyError);

    Split_Type = PyType_FromSpec(&Split_Type_Spec);
    PyModule_AddObject(m, "Split", Split_Type);

    Entry_Type = PyType_FromSpec(&Entry_Type_Spec);
    PyModule_AddObject(m, "Entry", Entry_Type);

    EntryList_Type = PyType_FromSpec(&EntryList_Type_Spec);
    PyModule_AddObject(m, "EntryList", EntryList_Type);

    Account_Type = PyType_FromSpec(&Account_Type_Spec);
    PyModule_AddObject(m, "Account", Account_Type);
    return m;
}

