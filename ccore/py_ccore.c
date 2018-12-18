#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "amount.h"
#include "split.h"
#include "transaction.h"
#include "account.h"
#include "util.h"

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
    Account *account;
    // If true, we own the Account instance and have to free it.
    bool owned;
} PyAccount;

static PyObject *Account_Type;
#define Account_Check(v) (Py_TYPE(v) == (PyTypeObject *)Account_Type)

/* Manages the list of Account in a document.
 *
 * Mostly, ensures that name uniqueness is enforced, manages name clashes on
 * new account creation.  `default_currency` is the currency that we want new
 * accounts (created in `find`) to have.
 */
typedef struct {
    PyObject_HEAD
    AccountList alist;
    PyObject *accounts;
    // accountname: PyEntryList mapping
    PyObject *entries;
} PyAccountList;

static PyObject *AccountList_Type;
#define AccountList_Check(v) (Py_TYPE(v) == (PyTypeObject *)AccountList_Type)

// Assignment of money to an Account within a Transaction.
typedef struct {
    PyObject_HEAD
    Split *split;
    // If true, we own the Split instance and have to free it.
    bool owned;
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
    Account *account;
    PyObject *entries;
    PyEntry *last_reconciled;
} PyEntryList;

static PyObject *EntryList_Type;

typedef struct {
    PyObject_HEAD
    Transaction txn;
} PyTransaction;

static PyObject *Transaction_Type;
#define Transaction_Check(v) (Py_TYPE(v) == (PyTypeObject *)Transaction_Type)

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

static bool
_strset(char **dst, PyObject *src)
{
    if (src == Py_None) {
        return strset(dst, NULL);
    } else {
        Py_ssize_t len;
        const char *s = PyUnicode_AsUTF8AndSize(src, &len);
        if (s == NULL) {
            return false;
        }
        // It's possible that we get a string that has an embedded \0 in it.
        // It's not going to fare well on the C side. Let's see if we have one
        // by comparing reported lengths.
        if (len != (Py_ssize_t)strlen(s)) {
            // different lengths! oh no! let's replace \0s with spaces. But
            // everything gets more complicated because Python gave us a const
            // char, so we need to copy the whole thing in a buffer.
            char *buf = malloc(len+1);
            // not strcpy, it will stop at the first \0!
            memcpy(buf, s, len);
            for (int i=0; i<len; i++) {
                if (buf[i] == '\0') {
                    buf[i] = ' ';
                }
            }
            buf[len] = '\0';
            bool res = strset(dst, buf);
            free(buf);
            return res;
        }
        return strset(dst, s);
    }
}

static bool
_strsetnn(char **dst, PyObject *src)
{
    if (_strset(dst, src)) {
        if (*dst == NULL) {
            *dst = "";
        }
        return true;
    } else {
        return false;
    }
}

static PyObject*
_strget(const char *src)
{
    if (src == NULL) {
        Py_RETURN_NONE;
    } else if (src[0] == '\0') {
        return PyUnicode_InternFromString("");
    } else {
        return PyUnicode_FromString(src);
    }
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

static PyObject*
lower_and_strip(PyObject *s)
{
    PyObject *lowered = PyObject_CallMethod(s, "lower", NULL);
    if (lowered == NULL) {
        return NULL;
    }
    PyObject *res = PyObject_CallMethod(lowered, "strip", NULL);
    Py_DECREF(lowered);
    return res;
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

/* Account */
static PyAccount*
_PyAccount_from_account(Account *account)
{
    PyAccount *res = (PyAccount *)PyType_GenericAlloc((PyTypeObject *)Account_Type, 0);
    res->account = account;
    res->owned = false;
    return res;
}

static PyObject *
PyAccount_name(PyAccount *self)
{
    return _strget(self->account->name);
}

static PyObject *
PyAccount_currency(PyAccount *self)
{
    int len;
    len = strlen(self->account->currency->code);
    return PyUnicode_DecodeASCII(self->account->currency->code, len, NULL);
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
    self->account->currency = cur;
    return 0;
}

static PyObject *
PyAccount_type(PyAccount *self)
{
    char *s;
    switch (self->account->type) {
        case ACCOUNT_ASSET: s = "asset"; break;
        case ACCOUNT_LIABILITY: s = "liability"; break;
        case ACCOUNT_INCOME: s = "income"; break;
        case ACCOUNT_EXPENSE: s = "expense"; break;
    }
    return PyUnicode_InternFromString(s);
}

static int
_PyAccount_str2type(const char *s)
{
    if (strcmp(s, "asset") == 0) {
        return ACCOUNT_ASSET;
    } else if (strcmp(s, "liability") == 0) {
        return ACCOUNT_LIABILITY;
    } else if (strcmp(s, "income") == 0) {
        return ACCOUNT_INCOME;
    } else if (strcmp(s, "expense") == 0) {
        return ACCOUNT_EXPENSE;
    } else {
        PyErr_SetString(PyExc_ValueError, "invalid type");
        return -1;
    }
}

static int
PyAccount_type_set(PyAccount *self, PyObject *value)
{
    PyObject *tmp = PyUnicode_AsASCIIString(value);
    if (tmp == NULL) {
        return -1;
    }
    char *s = PyBytes_AsString(tmp);
    int res = _PyAccount_str2type(s);
    if (res >= 0) {
        self->account->type = res;
        return 0;
    } else {
        PyErr_SetString(PyExc_ValueError, "invalid type");
        return -1;
    }
}

static PyObject *
PyAccount_reference(PyAccount *self)
{
    return _strget(self->account->reference);
}

static int
PyAccount_reference_set(PyAccount *self, PyObject *value)
{
    return _strset(&self->account->reference, value) ? 0 : -1;
}

static PyObject *
PyAccount_groupname(PyAccount *self)
{
    return _strget(self->account->groupname);
}

static int
PyAccount_groupname_set(PyAccount *self, PyObject *value)
{
    return _strset(&self->account->groupname, value) ? 0 : -1;
}

static PyObject *
PyAccount_account_number(PyAccount *self)
{
    return _strget(self->account->account_number);
}

static int
PyAccount_account_number_set(PyAccount *self, PyObject *value)
{
    return _strset(&self->account->account_number, value) ? 0 : -1;
}

static PyObject *
PyAccount_inactive(PyAccount *self)
{
    if (self->account->inactive) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static int
PyAccount_inactive_set(PyAccount *self, PyObject *value)
{
    self->account->inactive = PyObject_IsTrue(value);
    return 0;
}

static PyObject *
PyAccount_autocreated(PyAccount *self)
{
    if (self->account->autocreated) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PyAccount_notes(PyAccount *self)
{
    return _strget(self->account->notes);
}

static int
PyAccount_notes_set(PyAccount *self, PyObject *value)
{
    return _strset(&self->account->notes, value) ? 0 : -1;
}

static PyObject *
PyAccount_repr(PyAccount *self)
{
    return PyUnicode_FromFormat("Account(%s)", self->account->name);
}

static Py_hash_t
PyAccount_hash(PyAccount *self)
{
    return self->account->id;
}

static PyObject *
PyAccount_richcompare(PyAccount *a, PyObject *b, int op)
{
    if (!Account_Check(b)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if ((op == Py_EQ) || (op == Py_NE)) {
        // TODO: change this to name comparison
        bool match = a->account == ((PyAccount *)b)->account;
        if (op == Py_NE) {
            match = !match;
        }
        if (match) {
            Py_RETURN_TRUE;
        } else {
            Py_RETURN_FALSE;
        }
    } else {
        Py_RETURN_NOTIMPLEMENTED;
    }
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
    account_normalize_amount(self->account, &res);
    return create_amount(res.val, res.currency);
}

static PyObject*
PyAccount_is_balance_sheet_account(PyAccount *self, PyObject *args)
{
    if (account_is_balance_sheet(self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_credit_account(PyAccount *self, PyObject *args)
{
    if (account_is_credit(self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_debit_account(PyAccount *self, PyObject *args)
{
    if (account_is_debit(self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_is_income_statement_account(PyAccount *self, PyObject *args)
{
    if (account_is_income_statement(self->account)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject*
PyAccount_combined_display(PyAccount *self)
{
    if (self->account->account_number[0] != '\0') {
        return PyUnicode_FromFormat(
            "%s - %s", self->account->account_number, self->account->name);
    } else {
        return PyAccount_name(self);
    }
}

static PyObject *
PyAccount_copy(PyAccount *self)
{
    PyAccount *r = (PyAccount *)PyType_GenericAlloc((PyTypeObject *)Account_Type, 0);
    r->owned = true;
    r->account = malloc(sizeof(Account));
    memset(r->account, 0, sizeof(Account));
    account_copy(r->account, self->account);
    r->account->id = self->account->id;
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
    // Unless we own our Account through copy(), we don't dealloc our Account.
    // AccountList takes care of that.
    if (self->owned) {
        account_deinit(self->account);
        free(self->account);
    }
}

/* Split attrs */
static PyObject *
PySplit_reconciliation_date(PySplit *self)
{
    return time2pydate(self->split->reconciliation_date);
}

static int
PySplit_reconciliation_date_set(PySplit *self, PyObject *value)
{
    time_t res = pydate2time(value);
    if (res == 1) {
        return -1;
    } else {
        self->split->reconciliation_date = res;
        return 0;
    }
}

static PyObject *
PySplit_memo(PySplit *self)
{
    return _strget(self->split->memo);
}

static int
PySplit_memo_set(PySplit *self, PyObject *value)
{
    return _strset(&self->split->memo, value) ? 0 : -1;
}

static PyObject *
PySplit_reference(PySplit *self)
{
    return _strget(self->split->reference);
}

static int
PySplit_reference_set(PySplit *self, PyObject *value)
{
    return _strset(&self->split->reference, value) ? 0 : -1;
}

static PyObject *
PySplit_account(PySplit *self)
{
    if (self->split->account == NULL) {
        Py_RETURN_NONE;
    } else {
        return (PyObject *)_PyAccount_from_account(self->split->account);
    }
}

static int
PySplit_account_set(PySplit *self, PyObject *value)
{
    Account *newval = NULL;
    if (value != Py_None) {
        if (!Account_Check(value)) {
            PyErr_SetString(PyExc_ValueError, "not an account");
            return -1;
        }
        PyAccount *account = (PyAccount *)value;
        newval = account->account;
    }
    split_account_set(self->split, newval);
    return 0;
}

static PyObject *
PySplit_amount(PySplit *self)
{
    Split *split = self->split;
    return create_amount(split->amount.val, split->amount.currency);
}

static int
PySplit_amount_set(PySplit *self, PyObject *value)
{
    Amount *amount;

    amount = get_amount(value);
    split_amount_set(self->split, amount);
    return 0;
}

static PyObject *
PySplit_account_name(PySplit *self)
{
    if (self->split->account == NULL) {
        return PyUnicode_InternFromString("");
    } else {
        _strget(self->split->account->name);
    }
}

static PyObject *
PySplit_credit(PySplit *self)
{
    Amount *a = &self->split->amount;
    if (a->val < 0) {
        return create_amount(-a->val, a->currency);
    } else {
        return PyLong_FromLong(0);
    }
}

static PyObject *
PySplit_debit(PySplit *self)
{
    Amount *a = &self->split->amount;
    if (a->val > 0) {
        return create_amount(a->val, a->currency);
    } else {
        return PyLong_FromLong(0);
    }
}

static PyObject *
PySplit_reconciled(PySplit *self)
{
    if (self->split->reconciliation_date == 0) {
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

    self->split = malloc(sizeof(Split));
    self->owned = true;
    amount = get_amount(amount_p);
    split_init(self->split, NULL, amount);
    if (PySplit_account_set(self, account) != 0) {
        return -1;
    }
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
        "(Ois)", aname, self->split->amount.val,
        self->split->amount.currency->code);
    fmt = PyUnicode_FromString("Split(%r Amount(%r, %r))");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static void
PySplit_dealloc(PySplit *self)
{
    if (self->owned) {
        split_deinit(self->split);
        free(self->split);
        self->split = NULL;
    }
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
    if (!split_copy(self->split, ((PySplit *)other)->split)) {
        PyErr_SetString(PyExc_ValueError, "something wen't wrong");
        return NULL;
    }
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
    if ((self->split->amount.val > 0) == (((PySplit *)other)->split->amount.val > 0)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PySplit_copy(PySplit *self)
{
    PySplit *r = (PySplit *)PyType_GenericAlloc((PyTypeObject *)Split_Type, 0);
    r->split = malloc(sizeof(Split));
    r->owned = true;
    split_init(r->split, NULL, amount_zero());
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
        if (split->split->account != NULL) {
            PyObject *account = PySplit_account(split);
            PyList_Append(r, account);
            Py_DECREF(account);
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
    Amount *amount = get_amount(amount_p);
    split_amount_set(self->split->split, amount);
    Amount *other_amount = &other->split->amount;
    bool is_mct = false;
    if (!same_currency(amount, other_amount)) {
        bool is_asset = false;
        bool other_is_asset = false;
        Account *a = self->split->split->account;
        if (a != NULL) {
            is_asset = account_is_balance_sheet(a);
        }
        a = other->split->account;
        if (a != NULL) {
            other_is_asset = account_is_balance_sheet(a);
        }
        if (is_asset && other_is_asset) {
            is_mct = true;
        }
    }

    if (is_mct) {
        // don't touch other side unless we have a logical imbalance
        if ((self->split->split->amount.val > 0) == (other_amount->val > 0)) {
            Amount a;
            amount_copy(&a, other_amount);
            a.val *= -1;
            split_amount_set(other->split, &a);
        }
    } else {
        Amount a;
        amount_copy(&a, amount);
        a.val *= -1;
        split_amount_set(other->split, &a);
    }
    Py_RETURN_NONE;
}

static PyObject*
PyEntry_normal_balance(PyEntry *self, PyObject *args)
{
    Amount amount;
    amount_copy(&amount, &self->balance);
    Account *a = self->split->split->account;
    if (a != NULL) {
        if (account_is_credit(a)) {
            amount.val *= -1;
        }
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
static PyEntryList*
_PyEntryList_new(Account *account)
{
    PyEntryList *res = (PyEntryList *)PyType_GenericAlloc((PyTypeObject *)EntryList_Type, 0);
    res->account = account;
    res->entries = PyList_New(0);
    res->last_reconciled = NULL;
    return res;
}

static void
_PyEntryList_maybe_set_last_reconciled(PyEntryList *self, PyEntry *entry)
{
    // we don't bother increfing last_reconciled: implicit in entries'
    // membership
    if (entry->split->split->reconciliation_date != 0) {
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
            Amount *src = &entry->split->split->amount;
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
PyEntryList_normal_balance(PyEntryList *self, PyObject *args)
{
    PyObject *date = Py_None;
    char *currency = NULL;

    if (!PyArg_ParseTuple(args, "|Os", &date, &currency)) {
        return NULL;
    }
    Amount res;
    if (currency == NULL) {
        res.currency = self->account->currency;
    } else {
        res.currency = getcur(currency);
        if (res.currency == NULL) {
            return NULL;
        }
    }
    if (!_PyEntryList_balance(self, &res, date, false)) {
        return NULL;
    } else {
        account_normalize_amount(self->account, &res);
        return create_amount(res.val, res.currency);
    }
}

static PyObject*
PyEntryList_normal_balance_of_reconciled(PyEntryList *self, PyObject *args)
{
    Amount res;
    if (!_PyEntryList_balance_of_reconciled(self, &res)) {
        return NULL;
    } else {
        account_normalize_amount(self->account, &res);
        return create_amount(res.val, res.currency);
    }
}

static PyObject*
PyEntryList_normal_cash_flow(PyEntryList *self, PyObject *args)
{
    PyObject *daterange;
    char *currency = NULL;

    if (!PyArg_ParseTuple(args, "O|s", &daterange, &currency)) {
        return NULL;
    }
    Amount res;
    if (currency == NULL) {
        res.currency = self->account->currency;
    } else {
        res.currency = getcur(currency);
        if (res.currency == NULL) {
            return NULL;
        }
    }
    if (!_PyEntryList_cash_flow(self, &res, daterange)) {
        return NULL;
    } else {
        account_normalize_amount(self->account, &res);
        return create_amount(res.val, res.currency);
    }
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

/* PyAccountList */
static int
PyAccountList_init(PyAccountList *self, PyObject *args, PyObject *kwds)
{
    char *currency;

    static char *kwlist[] = {"default_currency", NULL};

    int res = PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &currency);
    if (!res) {
        return -1;
    }

    Currency *c = getcur(currency);
    if (c == NULL) {
        return -1;
    }
    accounts_init(&self->alist, 100, c);
    self->accounts = PyList_New(0);
    self->entries = PyDict_New();
    return 0;
}

static PyObject*
_PyAccountList_find_reference(PyAccountList *self, const char *reference)
{
    if (reference == NULL || strlen(reference) == 0) {
        Py_RETURN_NONE;
    }
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=0; i<len; i++) {
        PyAccount *account = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        char *val = account->account->reference;
        if (val == NULL) continue;
        if (strcmp(reference, val) == 0) {
            Py_INCREF(account);
            return (PyObject *)account;
        }
    }
    Py_RETURN_NONE;
}


static PyObject*
PyAccountList_clean_empty_categories(PyAccountList *self, PyObject *args)
{
    PyObject *from_account_p = NULL;
    Account *from_account = NULL;

    if (!PyArg_ParseTuple(args, "|O", &from_account_p)) {
        return NULL;
    }
    if (from_account_p != NULL && from_account_p != Py_None) {
        from_account = ((PyAccount *)from_account_p)->account;
    }
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=len-1; i>=0; i--) {
        PyAccount *account_p = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        Account *account = account_p->account;
        PyObject *entries = PyDict_GetItemString(self->entries, account->name);
        if (!account->autocreated) {
            continue;
        } else if (account == from_account) {
            continue;
        } else if (PySequence_Length(entries) > 0) {
            continue;
        }
        account->deleted = true;
        if (PyList_SetSlice(self->accounts, i, i+1, NULL) == -1) {
            return NULL;
        }
    }
    Py_RETURN_NONE;
}

static PyObject*
PyAccountList_clear(PyAccountList *self, PyObject *args)
{
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=len-1; i>=0; i--) {
        PyAccount *account = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        account->account->deleted = true;
    }
    if (PyList_SetSlice(self->accounts, 0, len, NULL) == -1) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject*
_PyAccountList_find(PyAccountList *self, PyObject *name)
{
    PyObject *normalized = lower_and_strip(name);
    if (normalized == NULL) {
        return NULL;
    }
    PyObject *res = NULL;
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=0; i<len; i++) {
        PyAccount *account = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        PyObject *aname = PyAccount_name(account);
        PyObject *anorm = lower_and_strip(aname);
        Py_DECREF(aname);
        if (anorm == NULL) {
            return NULL;
        }
        if (PyObject_RichCompareBool(anorm, normalized, Py_EQ) > 0) {
            res = (PyObject *)account;
            break;
        }
        PyObject *anum = PyAccount_account_number(account);
        if (PyObject_IsTrue(anum)) {
            PyObject *startswith = PyObject_CallMethod(
                normalized, "startswith", "O", anum);
            Py_DECREF(anum);
            int r = PyObject_IsTrue(startswith);
            Py_DECREF(startswith);
            if (r) {
                res = (PyObject *)account;
                break;
            }
        } else {
            Py_DECREF(anum);
        }
    }
    if (res != NULL) {
        Py_INCREF(res);
        return res;
    } else {
        Py_RETURN_NONE;
    }
}

static PyObject*
PyAccountList_create(PyAccountList *self, PyObject *args)
{
    PyObject *name, *currency, *type;

    if (!PyArg_ParseTuple(args, "OOO", &name, &currency, &type)) {
        return NULL;
    }
    PyObject *found = _PyAccountList_find(self, name);
    if (found == NULL) {
        return NULL;
    }
    if (found != Py_None) {
        PyErr_SetString(PyExc_ValueError, "Account name already in list");
        return NULL;
    }
    Py_DECREF(found);
    PyAccount *account = (PyAccount *)PyType_GenericAlloc((PyTypeObject *)Account_Type, 0);
    account->owned = false;
    Account *a = accounts_create(&self->alist);
    account->account = a;
    if (PyAccount_currency_set(account, currency) < 0) {
        a->id = 0;
        return NULL;
    }
    if (PyAccount_type_set(account, type) < 0) {
        a->id = 0;
        return NULL;
    }
    if (!_strset(&a->name, name)) {
        return NULL;
    }
    a->inactive = false;
    a->account_number = "";
    a->notes = "";
    a->autocreated = false;
    a->deleted = false;
    PyList_Append(self->accounts, (PyObject *)account);
    return (PyObject *)account;
}

static PyObject*
PyAccountList_create_from(PyAccountList *self, PyAccount *account)
{
    if (!Account_Check(account)) {
        return NULL;
    }
    if (account->account->name == NULL) {
        // Trying to copy from a deleted owned account. We should always copy
        // accounts when storing it "outside" (in an undoer, for example...)
        PyErr_SetString(PyExc_ValueError, "owned account was deleted! can't use.");
        return NULL;
    }
    if (PySequence_Contains(self->accounts, (PyObject *)account)) {
        Py_INCREF(account);
        return (PyObject *)account;
    }
    PyObject *found = _PyAccountList_find_reference(self, account->account->reference);
    if (found != Py_None) {
        return found;
    }
    Py_DECREF(found);
    // if an account (deleted or not) with the same name is present, let's
    // reuse the instance.
    Account *a = accounts_find_by_name(&self->alist, account->account->name);
    if (a == NULL) {
        // no account with the same name, we create a new account.
        a = accounts_create(&self->alist);
        account_copy(a, account->account);
    } else if (a != account->account) {
        // We found an Account with the same name, but this Account's strings
        // must be deallocated before we copy over them.
        // This is not done if both PyAccounts point to the same Account.
        account_deinit(a);
        account_copy(a, account->account);
    }
    // if we ended up finding a deleted account, let's undelete it. It's coming
    // back into service!
    a->deleted = false;
    PyAccount *res = _PyAccount_from_account(a);
    PyList_Append(self->accounts, (PyObject *)res);
    return (PyObject *)res;
}

static PyObject*
PyAccountList_entries_for_account(PyAccountList *self, PyAccount *account)
{
    if (!Account_Check(account)) {
        PyErr_SetString(PyExc_TypeError, "not an account");
        return NULL;
    }
    PyObject *res = PyDict_GetItemString(self->entries, account->account->name);
    if (res == NULL) {
        res = (PyObject *)_PyEntryList_new(account->account);
        PyDict_SetItemString(self->entries, account->account->name, res);
        Py_DECREF(res);
    }
    Py_INCREF(res);
    return res;
}

static PyObject*
PyAccountList_filter(PyAccountList *self, PyObject *args, PyObject *kwds)
{
    PyObject *groupname = NULL;
    char *type = NULL;
    static char *kwlist[] = {"groupname", "type", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "|Os", kwlist, &groupname, &type)) {
        return NULL;
    }
    PyObject *res = PySequence_List(self->accounts);
    if (groupname != NULL) {
        const char *tomatch;
        if (groupname == Py_None) {
            tomatch = NULL;
        } else {
            tomatch = PyUnicode_AsUTF8(groupname);
            if (tomatch == NULL) {
                return NULL;
            }
        }
        PyObject *newres = PyList_New(0);
        Py_ssize_t len = PyList_Size(res);
        for (int i=0; i<len; i++) {
            PyAccount *account = (PyAccount *)PyList_GetItem(res, i); // borrowed
            char *g = account->account->groupname;
            if (tomatch == NULL) {
                if (g == NULL) {
                    PyList_Append(newres, (PyObject *)account);
                }
            } else {
                if (g != NULL && (strcmp(g, tomatch) == 0)) {
                    PyList_Append(newres, (PyObject *)account);
                }
            }
        }
        Py_DECREF(res);
        res = newres;
    }
    if (type != NULL) {
        int t = _PyAccount_str2type(type);
        if (t < 0) {
            return NULL;
        }
        PyObject *newres = PyList_New(0);
        Py_ssize_t len = PyList_Size(res);
        for (int i=0; i<len; i++) {
            PyAccount *account = (PyAccount *)PyList_GetItem(res, i); // borrowed
            if (account->account->type == (AccountType)t) {
                PyList_Append(newres, (PyObject *)account);
            }
        }
        Py_DECREF(res);
        res = newres;
    }
    return res;
}

static PyObject*
PyAccountList_find(PyAccountList *self, PyObject *args)
{
    PyObject *name;
    PyObject *type = NULL;

    if (!PyArg_ParseTuple(args, "O|O", &name, &type)) {
        return NULL;
    }
    PyObject *res = _PyAccountList_find(self, name);
    if (res == NULL) {
        return NULL;
    }
    if (res != Py_None) {
        Py_INCREF(res);
        return res;
    }
    if (type == NULL) {
        Py_RETURN_NONE;
    }
    PyObject *aname = PyObject_CallMethod(name, "strip", NULL);
    PyObject *ccode = PyUnicode_FromString(self->alist.default_currency->code);
    PyObject *newargs = PyTuple_Pack(3, aname, ccode, type);
    Py_DECREF(aname);
    Py_DECREF(ccode);
    PyAccount *account = (PyAccount *)PyAccountList_create(self, newargs);
    Py_DECREF(newargs);
    account->account->autocreated = true;
    return (PyObject *)account;
}

static PyObject*
PyAccountList_find_reference(PyAccountList *self, PyObject *reference)
{
    const char *s = PyUnicode_AsUTF8(reference);
    if (s == NULL) {
        return NULL;
    }
    return _PyAccountList_find_reference(self, s);
}

static PyObject*
PyAccountList_has_multiple_currencies(PyAccountList *self, PyObject *args)
{
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=0; i<len; i++) {
        PyAccount *account = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        if (account->account->currency != self->alist.default_currency) {
            Py_RETURN_TRUE;
        }
    }
    Py_RETURN_FALSE;
}

static PyObject*
PyAccountList_new_name(PyAccountList *self, PyObject *base_name)
{
    PyObject *name = base_name;
    Py_INCREF(name);
    int index = 0;
    while (1) {
        PyObject *found = _PyAccountList_find(self, name);
        if (found == NULL) {
            return NULL;
        }
        if (found == Py_None) {
            Py_DECREF(found);
            return name;
        }
        Py_DECREF(found);
        Py_DECREF(name);
        index++;
        name = PyUnicode_FromFormat("%S %d", base_name, index);
    }
}

// Borrowed
static PyAccount*
_PyAccountList_find_by_inner_pointer(PyAccountList *self, Account *p)
{
    Py_ssize_t len = PyList_Size(self->accounts);
    for (int i=0; i<len; i++) {
        PyAccount *account = (PyAccount *)PyList_GetItem(self->accounts, i); // borrowed
        if (account->account == p) {
            return account;
        }
    }
    return NULL;
}

static PyObject*
PyAccountList_remove(PyAccountList *self, PyAccount *account)
{
    if (!Account_Check(account)) {
        PyErr_SetString(PyExc_ValueError, "not an account");
        return NULL;
    }
    char *name = ((PyAccount *)account)->account->name;
    if (name == NULL) {
        PyErr_SetString(PyExc_ValueError, "deleted account");
        return NULL;
    }
    Account *a = accounts_find_by_name(&self->alist,name);
    if (a == NULL) {
        PyErr_SetString(PyExc_ValueError, "account not in list");
        return NULL;
    }
    if (a->deleted) {
        PyErr_SetString(PyExc_ValueError, "account already deleted");
        return NULL;
    }
    PyAccount *todelete = _PyAccountList_find_by_inner_pointer(self, a); // borrowed
    if (todelete == NULL) {
        PyErr_SetString(PyExc_ValueError, "something's wrong");
        return NULL;
    }
    if (PyObject_CallMethod(self->accounts, "remove", "O", todelete) == NULL) {
        return NULL;
    }
    a->deleted = true;
    Py_RETURN_NONE;
    // If account is owned, it will take care of its deallocation. If it's not
    // owned, we should deallocate it now to free a slot in its AccountList.
    /* if (!account->owned) {
     *   account_deinit(account->account);
     * }
     */
    // Actually, we don't do it. When considering the need for undo/redo, we
    // end up with tons of references to accounts that might have been deleted.
    // In the near future, I hope to straigten out this situation, bur for now,
    // we simply don't delete them.
}

static PyObject*
PyAccountList_rename_account(PyAccountList *self, PyObject *args)
{
    PyAccount *account;
    PyObject *newname;

    if (!PyArg_ParseTuple(args, "OO", &account, &newname)) {
        return NULL;
    }

    // TODO handle name clash
    Account *a = account->account;
    PyObject *entries = PyDict_GetItemString(self->entries, a->name);
    if (entries == NULL) {
        return NULL;
    }
    PyDict_SetItem(self->entries, newname, entries);
    PyDict_DelItemString(self->entries, a->name);
    _strset(&a->name, newname);
    Py_RETURN_NONE;
}

static PyObject*
PyAccountList_iter(PyAccountList *self)
{
    return PyObject_GetIter(self->accounts);
}

static Py_ssize_t
PyAccountList_len(PyAccountList *self)
{
    return PyList_Size(self->accounts);
}

static int
PyAccountList_contains(PyAccountList *self, PyObject *account)
{
    if (!Account_Check(account)) {
        return 0;
    }
    char *name = ((PyAccount *)account)->account->name;
    if (name == NULL) {
        return 0;
    }
    Account *a = accounts_find_by_name(&self->alist, name);
    if ((a != NULL) && !a->deleted){
        return 1;
    } else {
        return 0;
    }
}

static PyObject *
PyAccountList_default_currency(PyAccountList *self)
{
    int len;
    len = strlen(self->alist.default_currency->code);
    return PyUnicode_DecodeASCII(self->alist.default_currency->code, len, NULL);
}

static int
PyAccountList_default_currency_set(PyAccountList *self, PyObject *value)
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
    self->alist.default_currency = cur;
    return 0;
}

static void
PyAccountList_dealloc(PyAccountList *self)
{
    Py_DECREF(self->accounts);
    Py_DECREF(self->entries);
    accounts_deinit(&self->alist);
}

/* Transaction */
static PyObject *
PyTransaction_date(PyTransaction *self)
{
    return time2pydate(self->txn.date);
}

static int
PyTransaction_date_set(PyTransaction *self, PyObject *value)
{
    time_t res = pydate2time(value);
    if (res == 1) {
        return -1;
    } else {
        self->txn.date = res;
        return 0;
    }
}

static PyObject *
PyTransaction_description(PyTransaction *self)
{
    return _strget(self->txn.description);
}

static int
PyTransaction_description_set(PyTransaction *self, PyObject *value)
{
    return _strsetnn(&self->txn.description, value) ? 0 : -1;
}

static PyObject *
PyTransaction_payee(PyTransaction *self)
{
    return _strget(self->txn.payee);
}

static int
PyTransaction_payee_set(PyTransaction *self, PyObject *value)
{
    return _strsetnn(&self->txn.payee, value) ? 0 : -1;
}

static PyObject *
PyTransaction_checkno(PyTransaction *self)
{
    return _strget(self->txn.checkno);
}

static int
PyTransaction_checkno_set(PyTransaction *self, PyObject *value)
{
    return _strsetnn(&self->txn.checkno, value) ? 0 : -1;
}

static PyObject *
PyTransaction_notes(PyTransaction *self)
{
    return _strget(self->txn.notes);
}

static int
PyTransaction_notes_set(PyTransaction *self, PyObject *value)
{
    return _strsetnn(&self->txn.notes, value) ? 0 : -1;
}

static PyObject *
PyTransaction_position(PyTransaction *self)
{
    return PyLong_FromLong(self->txn.position);
}

static int
PyTransaction_position_set(PyTransaction *self, PyObject *value)
{
    self->txn.position = PyLong_AsLong(value);
    return 0;
}

static PyObject *
PyTransaction_mtime(PyTransaction *self)
{
    return PyLong_FromLong(self->txn.mtime);
}

static int
PyTransaction_mtime_set(PyTransaction *self, PyObject *value)
{
    if (!PyLong_Check(value)) {
        // float from time.time()
        PyObject *truncated = PyNumber_Long(value);
        if (truncated == NULL) {
            return -1;
        }
        self->txn.mtime = PyLong_AsLong(truncated);
        Py_DECREF(truncated);
    } else {
        self->txn.mtime = PyLong_AsLong(value);
    }
    return 0;
}

static PyObject *
PyTransaction_copy_from(PyTransaction *self, PyTransaction *other)
{
    if (!transaction_copy(&self->txn, &other->txn)) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static int
PyTransaction_init(PyTransaction *self, PyObject *args, PyObject *kwds)
{
    PyObject *date_p, *description, *payee, *checkno;

    static char *kwlist[] = {"date", "description", "payee", "checkno", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "O|OOO", kwlist, &date_p, &description, &payee, &checkno);
    if (!res) {
        return -1;
    }

    time_t date = pydate2time(date_p);
    if (date == 1) {
        return -1;
    }
    transaction_init(&self->txn, date);
    PyTransaction_description_set(self, description);
    PyTransaction_payee_set(self, payee);
    PyTransaction_checkno_set(self, checkno);
    return 0;
}

static void
PyTransaction_dealloc(PyTransaction *self)
{
}

/* Oven functions */

static bool
_py_oven_cook_splits(
    PyObject *splitpairs, PyEntryList *entries)
{
    Amount amount;
    Amount balance;
    Amount balance_with_budget;
    Amount reconciled_balance;

    balance.currency = entries->account->currency;
    balance_with_budget.currency = balance.currency;
    reconciled_balance.currency = balance.currency;
    amount.currency = balance.currency;

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

        Split *split = entry->split->split;
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
        if (entry->split->split->reconciliation_date != 0) {
            reconciled_balance.val += entry->split->split->amount.val;
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
py_oven_cook_txns(PyObject *self, PyObject *args)
{
    PyAccountList *accounts;
    PyObject *txns;

    if (!PyArg_ParseTuple(args, "OO", &accounts, &txns)) {
        return NULL;
    }
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
            PySplit *split_p = (PySplit *)PyList_GetItem(splits, j); // borrowed
            Split *split = split_p->split;
            if (split->account == NULL) {
                continue;
            }
            PyObject *splitpairs = PyDict_GetItemString(
                a2s, split->account->name); // borrowed
            if (splitpairs == NULL) {
                splitpairs = PyList_New(0);
                PyDict_SetItemString(a2s, split->account->name, splitpairs);
                Py_DECREF(splitpairs);
            }
            PyObject *pair = PyTuple_Pack(2, txn, split_p);
            PyList_Append(splitpairs, pair);
            Py_DECREF(pair);
        }
    }

    Py_ssize_t pos = 0;
    PyObject *k, *v;
    while (PyDict_Next(a2s, &pos, &k, &v)) {
        char *aname = PyUnicode_AsUTF8(k);
        Account *account = accounts_find_by_name(&accounts->alist, aname);
        if (account == NULL) {
            PyErr_SetString(PyExc_ValueError, "integrity error in split accounts");
            return NULL;
        }
        PyEntryList *entries = (PyEntryList *)PyDict_GetItemString(
            accounts->entries, aname); // borrowed
        if (entries == NULL) {
            entries = _PyEntryList_new(account);
            PyDict_SetItemString(accounts->entries, aname, (PyObject *)entries);
            Py_DECREF(entries);
        }
        if (!_py_oven_cook_splits(v, entries)) {
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
    {"oven_cook_txns", py_oven_cook_txns, METH_VARARGS},
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
    {"normal_balance", (PyCFunction)PyEntryList_normal_balance, METH_VARARGS, ""},
    {"normal_balance_of_reconciled", (PyCFunction)PyEntryList_normal_balance_of_reconciled, METH_NOARGS, ""},
    {"normal_cash_flow", (PyCFunction)PyEntryList_normal_cash_flow, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyType_Slot EntryList_Slots[] = {
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
    {"name", (getter)PyAccount_name, NULL, NULL, NULL},
    {"reference", (getter)PyAccount_reference, (setter)PyAccount_reference_set, NULL, NULL},
    {"groupname", (getter)PyAccount_groupname, (setter)PyAccount_groupname_set, NULL, NULL},
    {"account_number", (getter)PyAccount_account_number, (setter)PyAccount_account_number_set, NULL, NULL},
    {"inactive", (getter)PyAccount_inactive, (setter)PyAccount_inactive_set, NULL, NULL},
    {"notes", (getter)PyAccount_notes, (setter)PyAccount_notes_set, NULL, NULL},
    {"autocreated", (getter)PyAccount_autocreated, NULL, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Account_Slots[] = {
    {Py_tp_methods, PyAccount_methods},
    {Py_tp_getset, PyAccount_getseters},
    {Py_tp_hash, PyAccount_hash},
    {Py_tp_repr, PyAccount_repr},
    {Py_tp_richcompare, PyAccount_richcompare},
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

static PyMethodDef PyAccountList_methods[] = {
    {"clean_empty_categories", (PyCFunction)PyAccountList_clean_empty_categories, METH_VARARGS, ""},
    {"clear", (PyCFunction)PyAccountList_clear, METH_NOARGS, ""},
    {"create", (PyCFunction)PyAccountList_create, METH_VARARGS, ""},
    {"create_from", (PyCFunction)PyAccountList_create_from, METH_O, ""},
    {"entries_for_account", (PyCFunction)PyAccountList_entries_for_account, METH_O, ""},
    // Returns all accounts of the given `type` and/or `groupname`.
    {"filter", (PyCFunction)PyAccountList_filter, METH_VARARGS|METH_KEYWORDS, ""},
    // Returns the first account matching with ``name`` (case insensitive)
    // If `auto_create_type` is specified and no account is found, create an
    // account of type `auto_create_type` and return it.
    {"find", (PyCFunction)PyAccountList_find, METH_VARARGS, ""},
    // Returns the account with `reference` or `None` if it isn't there.
    {"find_reference", (PyCFunction)PyAccountList_find_reference, METH_O, ""},
    // Returns whether there's at least one account with a different currency.
    // ... that is, a currency other than `default_currency`.
    {"has_multiple_currencies", (PyCFunction)PyAccountList_has_multiple_currencies, METH_NOARGS, ""},
    // Returns a unique name from ``base_name``.
    // If `base_name` already exists, append an incrementing number to it until
    // we find a unique name.
    {"new_name", (PyCFunction)PyAccountList_new_name, METH_O, ""},
    {"remove", (PyCFunction)PyAccountList_remove, METH_O, ""},
    {"rename_account", (PyCFunction)PyAccountList_rename_account, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyAccountList_getseters[] = {
    {"default_currency", (getter)PyAccountList_default_currency, (setter)PyAccountList_default_currency_set, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot AccountList_Slots[] = {
    {Py_tp_init, PyAccountList_init},
    {Py_tp_methods, PyAccountList_methods},
    {Py_tp_getset, PyAccountList_getseters},
    {Py_sq_length, PyAccountList_len},
    {Py_sq_contains, PyAccountList_contains},
    {Py_tp_iter, PyAccountList_iter},
    {Py_tp_dealloc, PyAccountList_dealloc},
    {0, 0},
};

PyType_Spec AccountList_Type_Spec = {
    "_ccore.AccountList",
    sizeof(PyAccountList),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    AccountList_Slots,
};

static PyMethodDef PyTransaction_methods[] = {
    {"copy_from", (PyCFunction)PyTransaction_copy_from, METH_O, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyTransaction_getseters[] = {
    {"date", (getter)PyTransaction_date, (setter)PyTransaction_date_set, NULL, NULL},
    {"description", (getter)PyTransaction_description, (setter)PyTransaction_description_set, NULL, NULL},
    {"payee", (getter)PyTransaction_payee, (setter)PyTransaction_payee_set, NULL, NULL},
    {"checkno", (getter)PyTransaction_checkno, (setter)PyTransaction_checkno_set, NULL, NULL},
    {"notes", (getter)PyTransaction_notes, (setter)PyTransaction_notes_set, NULL, NULL},
    {"position", (getter)PyTransaction_position, (setter)PyTransaction_position_set, NULL, NULL},
    {"mtime", (getter)PyTransaction_mtime, (setter)PyTransaction_mtime_set, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Transaction_Slots[] = {
    {Py_tp_init, PyTransaction_init},
    {Py_tp_methods, PyTransaction_methods},
    {Py_tp_getset, PyTransaction_getseters},
    {Py_tp_dealloc, PyTransaction_dealloc},
    {0, 0},
};

PyType_Spec Transaction_Type_Spec = {
    "_ccore.Transaction",
    sizeof(PyTransaction),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Transaction_Slots,
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

    Account_Type = PyType_FromSpec(&Account_Type_Spec);

    AccountList_Type = PyType_FromSpec(&AccountList_Type_Spec);
    PyModule_AddObject(m, "AccountList", AccountList_Type);

    Transaction_Type = PyType_FromSpec(&Transaction_Type_Spec);
    PyModule_AddObject(m, "Transaction", Transaction_Type);
    return m;
}
