#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "amount.h"
#include "split.h"
#include "transaction.h"

/* Types */
static PyObject *UnsupportedCurrencyError = NULL;

typedef struct {
    PyObject_HEAD
    Amount amount;
} PyAmount;

static PyObject *Amount_Type;
#define Amount_Check(v) (Py_TYPE(v) == (PyTypeObject *)Amount_Type)

// Assignment of money to an Account within a Transaction.
typedef struct {
    PyObject_HEAD
    Split split;
    PyObject *account;
    // Freeform memo about that split.
    PyObject *memo;
    // Date at which the user reconciled this split with an external source.
    PyObject *reconciliation_date;
    // Unique reference from an external source.
    PyObject *reference;
} PySplit;

static PyObject *Split_Type;
#define Split_Check(v) (Py_TYPE(v) == (PyTypeObject *)Split_Type)

/* Wrapper around a Split to show in an Account ledger.
 *
 * The two main roles of the entre as a wrapper is to handle user edits and
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
    // Amount that we move. Entry has its own `amount` because we might have to
    // convert `Split.amount` in another currency (the currency of the account,
    // in which we'll want to display that amount).
    Amount amount;
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

/* Utils */
static bool
pydate2tm(PyObject *pydate, struct tm *dest)
{
    if (!PyDate_Check(pydate)) {
        PyErr_SetString(PyExc_ValueError, "pydate2tm needs a date value");
        return false;
    }
    dest->tm_year = PyDateTime_GET_YEAR(pydate) - 1900;
    dest->tm_mon = PyDateTime_GET_MONTH(pydate) - 1;
    dest->tm_mday = PyDateTime_GET_DAY(pydate);
    return true;
}

static PyObject*
tm2pydate(struct tm *date)
{
    return PyDate_FromDate(date->tm_year + 1900, date->tm_mon + 1, date->tm_mday);
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
    if (!pydate2tm(pydate, &date)) {
        return 1;
    }
    return mktime(&date);
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

static int
check_amount(PyObject *o)
{
    /* Returns true if o is an amount and false otherwise.
       A valid amount is either an PyAmount instance or an int instance with the value of 0.
    */
    if (Amount_Check(o)) {
        return 1;
    }
    if (!PyLong_Check(o)) {
        return 0;
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

    PyDateTime_IMPORT;
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

    PyDateTime_IMPORT;
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
    struct tm date = {0};
    char *code1, *code2;
    Currency *c1, *c2;
    double rate;

    if (!PyArg_ParseTuple(args, "Oss", &pydate, &code1, &code2)) {
        return NULL;
    }

    if (!pydate2tm(pydate, &date)) {
        return NULL;
    }

    c1 = currency_get(code1);
    c2 = currency_get(code2);
    if (c1 == NULL || c2 == NULL) {
        // Something's wrong, let's just return 1
        return PyLong_FromLong(1);
    }
    if (currency_getrate(&date, c1, c2, &rate) != CURRENCY_OK) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return PyFloat_FromDouble(rate);
}

static PyObject*
py_currency_set_CAD_value(PyObject *self, PyObject *args)
{
    PyObject *pydate;
    struct tm date = {0};
    char *code;
    Currency *c;
    double rate;

    if (!PyArg_ParseTuple(args, "Osd", &pydate, &code, &rate)) {
        return NULL;
    }

    if (!pydate2tm(pydate, &date)) {
        return NULL;
    }

    c = getcur(code);
    if (c == NULL) {
        return NULL;
    }

    currency_set_CAD_value(&date, c, rate);
    Py_INCREF(Py_None);
    return Py_None;
}

static PyObject*
py_currency_daterange(PyObject *self, PyObject *args)
{
    char *code;
    Currency *c;
    struct tm start = {0};
    struct tm stop = {0};
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

    pystart = tm2pydate(&start);
    pystop = tm2pydate(&stop);
    res = PyTuple_Pack(2, pystart, pystop);
    Py_DECREF(pystart);
    Py_DECREF(pystop);
    return res;
}

static PyObject *
py_currency_exponent(PyObject *self, PyObject *args)
{
    char *code;
    Currency *c;

    if (!PyArg_ParseTuple(args, "s", &code)) {
        return NULL;
    }

    c = getcur(code);
    if (c == NULL) {
        return NULL;
    }

    return PyLong_FromLong(c->exponent);
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

static PyObject *
PyAmount_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
    PyAmount *self;

    self = (PyAmount *)PyType_GenericAlloc(type, 0);
    if (self == NULL) {
        return NULL;
    }
    self->amount.val = 0;
    self->amount.currency = NULL;
    return (PyObject *)self;
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

    c = currency_get(code);
    if (c == NULL) {
        PyErr_SetString(PyExc_ValueError, "couldn't find currency code");
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
            c = currency_get(zero_currency);
            if (c == NULL) {
                PyErr_SetString(PyExc_ValueError, "currency not found");
                return NULL;
            }
            amount->currency = c;
        } else {
            amount->currency = NULL;
        }
    }
    if (strlen(default_currency)) {
        c = currency_get(default_currency);
        if (c == NULL) {
            PyErr_SetString(PyExc_ValueError, "currency not found");
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
    struct tm date = {0};
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
    if (!pydate2tm(pydate, &date)) {
        return NULL;
    }
    if (!amount_convert(&dest, amount, &date)) {
        PyErr_SetString(PyExc_ValueError, "problems getting a rate");
        return NULL;
    }
    return create_amount(dest.val, dest.currency);
}

/* Split attrs */
static PyObject *
PySplit_reconciliation_date(PySplit *self)
{
    Py_INCREF(self->reconciliation_date);
    return self->reconciliation_date;
}

static int
PySplit_reconciliation_date_set(PySplit *self, PyObject *value)
{
    Py_XDECREF(self->reconciliation_date);
    self->reconciliation_date = value;
    Py_INCREF(self->reconciliation_date);
    return 0;
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
    return self->account;
}

static int
PySplit_account_set(PySplit *self, PyObject *value)
{
    if (value == self->account) {
        return 0;
    }
    int account_id = 0;
    if (value != Py_None) {
        PyObject *tmp = PyObject_GetAttrString(value, "id");
        if (tmp == NULL) {
            return -1;
        }
        account_id = PyLong_AsLong(tmp);
        Py_DECREF(tmp);
        if (account_id == -1) {
            return -1;
        }
    }
    self->split.account_id = account_id;
    Py_XDECREF(self->account);
    self->account = value;
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
    if (self->account == Py_None) {
        return PyUnicode_InternFromString("");
    } else {
        return PyObject_GetAttrString(self->account, "name");
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
    if (self->reconciliation_date == Py_None) {
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

    self->reconciliation_date = NULL;
    self->account = NULL;
    if (PySplit_account_set(self, account) != 0) {
        Py_DECREF(self->reconciliation_date);
        return -1;
    }
    amount = get_amount(amount_p);
    amount_copy(&self->split.amount, amount);
    self->memo = PyUnicode_InternFromString("");
    self->reconciliation_date = Py_None;
    Py_INCREF(self->reconciliation_date);
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
    PySplit_account_set(self, ((PySplit *)other)->account);
    amount_copy(&self->split.amount, &((PySplit *)other)->split.amount);
    self->memo = ((PySplit *)other)->memo;
    Py_INCREF(self->memo);
    self->reconciliation_date = ((PySplit *)other)->reconciliation_date;
    Py_INCREF(self->reconciliation_date);
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
    r->reconciliation_date = NULL;
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

    static char *kwlist[] = {"split", "transaction", "amount", "balance",
        "reconciled_balance", "balance_with_budget", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OOOOOO", kwlist, &self->split, &self->transaction,
        &amount_p, &balance, &reconciled_balance, &balance_with_budget);
    if (!res) {
        return -1;
    }

    Py_INCREF(self->split);
    Py_INCREF(self->transaction);
    amount = get_amount(amount_p);
    amount_copy(&self->amount, amount);
    amount = get_amount(balance);
    amount_copy(&self->balance, amount);
    amount = get_amount(reconciled_balance);
    amount_copy(&self->reconciled_balance, amount);
    amount = get_amount(balance_with_budget);
    amount_copy(&self->balance_with_budget, amount);
    self->index = -1;
    return 0;
}

static PyObject *
PyEntry_richcompare(PyEntry *a, PyObject *b, int op)
{
    if (op != Py_EQ) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if (!Entry_Check(b)) {
        Py_RETURN_FALSE;
    }
    if (a->split == ((PyEntry *)b)->split) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
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

static PyObject *
PyEntry_account(PyEntry *self)
{
    return PySplit_account(self->split);
}

static PyObject *
PyEntry_amount(PyEntry *self)
{
    return create_amount(self->amount.val, self->amount.currency);
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

static int
PyEntry_index_set(PyEntry *self, PyObject *value)
{
    self->index = PyLong_AsLong(value);
    if (PyErr_Occurred()) {
        return -1;
    } else {
        return 0;
    }
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
PyEntry_reconciliation_key(PyEntry *self)
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
        if (split->account != Py_None) {
            PyList_Append(r, split->account);
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
    amount_copy(&r->amount, &self->amount);
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

/* Oven functions */

/* "Cook" splits into Entry with running balances
 *
 * This takes a list of (txn, split) pairs to cook as well as the account to
 * cook for. Returns a tuple (txn, split, balance)
 */
static PyObject*
py_oven_cook_splits(PyObject *self, PyObject *args)
{
    PyObject *splitpairs, *account, *tmp, *tmp2;
    Amount amount;
    Amount balance;
    Amount balance_with_budget;

    if (!PyArg_ParseTuple(args, "OO", &splitpairs, &account)) {
        return NULL;
    }

    tmp = PyObject_GetAttrString(account, "entries");
    if (tmp == NULL) {
        return NULL;
    }
    tmp2 = PyObject_CallMethod(tmp, "balance", NULL);
    if (tmp2 == NULL) {
        Py_DECREF(tmp);
        return NULL;
    }
    amount_copy(&balance, get_amount(tmp2));
    Py_DECREF(tmp2);
    tmp2 = PyObject_CallMethod(tmp, "balance_with_budget", NULL);
    Py_DECREF(tmp);
    if (tmp2 == NULL) {
        return NULL;
    }
    amount_copy(&balance_with_budget, get_amount(tmp2));
    Py_DECREF(tmp2);

    if (balance.currency == NULL) {
        tmp = PyObject_GetAttrString(account, "currency");
        if (tmp == NULL) {
            return NULL;
        }
        balance.currency = currency_get(PyUnicode_AsUTF8(tmp));
        Py_DECREF(tmp);
        if (balance.currency == NULL) {
            return NULL;
        }
    }
    balance_with_budget.currency = balance.currency;
    amount.currency = balance.currency;

    PyObject *iter = PyObject_GetIter(splitpairs);
    if (iter == NULL) {
        return NULL;
    }
    PyObject *res = PyList_New(PySequence_Length(splitpairs));
    int index = 0;
    PyObject *item;
    while (item = PyIter_Next(iter)) {
        /* Even though we use "item" below, we simplify our logic my decrefing
         * it right now. We can do this because "splitpairs" holds onto it so
         * we know it's not going to be freed.
         */
        Py_DECREF(item);
        PyObject *txn = PyTuple_GetItem(item, 0); // borrowed
        if (txn == NULL) {
            break;
        }
        PyObject *split_p = PyTuple_GetItem(item, 1); // borrowed
        if (split_p == NULL) {
            break;
        }
        tmp = PyObject_GetAttrString(txn, "TYPE");
        if (tmp == NULL) {
            break;
        }
        int txn_type = PyLong_AsLong(tmp);
        Py_DECREF(tmp);
        tmp = PyObject_GetAttrString(txn, "date");
        if (tmp == NULL) {
            break;
        }
        struct tm date = {0};
        if (!pydate2tm(tmp, &date)) {
            return NULL;
        }
        Py_DECREF(tmp);

        Split *split = &((PySplit *)split_p)->split;
        if (!amount_convert(&amount, &split->amount, &date)) {
            break;
        }
        if (txn_type != TXN_TYPE_BUDGET) {
            balance.val += amount.val;
        }
        balance_with_budget.val += amount.val;
        PyObject *balance_p = create_amount(balance.val, balance.currency);
        if (balance_p == NULL) {
            break;
        }
        PyObject *balance_with_budget_p = create_amount(
            balance_with_budget.val, balance_with_budget.currency);
        if (balance_with_budget_p == NULL) {
            break;
        }
        tmp = PyTuple_Pack(4, txn, split_p, balance_p, balance_with_budget_p);
        Py_DECREF(balance_p);
        Py_DECREF(balance_with_budget_p);
        PyList_SetItem(res, index, tmp);
        index++;
    }
    Py_DECREF(iter);
    if (PyErr_Occurred()) {
        return NULL;
    } else {
        return res;
    }
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
    {Py_tp_new, PyAmount_new},
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
    {"index", (getter)PyEntry_index, (setter)PyEntry_index_set, NULL, NULL},
    {"mtime", (getter)PyEntry_mtime, NULL, NULL, NULL},
    {"payee", (getter)PyEntry_payee, NULL, NULL, NULL},
    {"reconciled", (getter)PyEntry_reconciled, NULL, NULL, NULL},
    {"reconciled_balance", (getter)PyEntry_reconciled_balance, NULL, NULL, NULL},
    {"reconciliation_date", (getter)PyEntry_reconciliation_date, NULL, NULL, NULL},
    {"reconciliation_key", (getter)PyEntry_reconciliation_key, NULL, NULL, NULL},
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
    {"currency_exponent", py_currency_exponent, METH_VARARGS},
    {"oven_cook_splits", py_oven_cook_splits, METH_VARARGS},
    {NULL}  /* Sentinel */
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
    return m;
}

