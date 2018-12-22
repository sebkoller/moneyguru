#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "amount.h"
#include "entry.h"
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

typedef struct {
    PyObject_HEAD
    Transaction txn;
} PyTransaction;

static PyObject *Transaction_Type;

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
    Entry entry;
    PyTransaction *txn;
} PyEntry;

static PyObject *Entry_Type;
#define Entry_Check(v) (Py_TYPE(v) == (PyTypeObject *)Entry_Type)

typedef struct {
    PyObject_HEAD
    Account *account;
    PyObject *entries;
    Entry *last_reconciled;
    // This is a temporary buffer created on the fly by _PyEntryList_entries
    // and only to be used to short-term stuff.
    EntryList tmplist;
} PyEntryList;

static PyObject *EntryList_Type;

typedef struct {
    PyObject_HEAD
    PyObject *txns;
} PyTransactionList;

static PyObject *TransactionList_Type;

/* Utils */
static PyObject*
time2pydate(time_t date)
{
    if (date == 0) {
        Py_RETURN_NONE;
    }
    struct tm *d = gmtime(&date);
    if (d == NULL) {
        return PyErr_Format(
            PyExc_ValueError,
            "Couldn't convert time_t %ld\n",
            date);
    }
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
    time_t r = mktime(&date);
    return r;
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

static const Amount*
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

static PyObject *
create_amount(int64_t ival, Currency *currency)
{
    if (currency == NULL) {
        return PyLong_FromLong(0);
    }
    /* Create a new amount in a way that is faster than the normal init */
    PyAmount *r;

    r = (PyAmount *)PyType_GenericAlloc((PyTypeObject *)Amount_Type, 0);
    r->amount.val = ival;
    r->amount.currency = currency;
    return (PyObject *)r;
}

static PyObject *
pyamount(const Amount *amount)
{
    return create_amount(amount->val, amount->currency);
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

    Amount amount;
    amount_copy(&amount, get_amount(pyamount));
    if (!amount.val) {
        if (strlen(zero_currency)) {
            c = getcur(zero_currency);
            if (c == NULL) {
                return NULL;
            }
            amount.currency = c;
        } else {
            amount.currency = NULL;
        }
    }
    if (strlen(default_currency)) {
        c = getcur(default_currency);
        if (c == NULL) {
            return NULL;
        }
        show_currency = c != amount.currency;
    } else {
        show_currency = amount.currency != NULL;
    }
    rc = amount_format(
        result, &amount, show_currency, blank_zero, decimal_sep[0],
        grouping_sep[0]);
    if (!rc) {
        PyErr_SetString(PyExc_ValueError, "something went wrong");
        return NULL;
    }
    rc = strlen(result);
    return PyUnicode_DecodeUTF8(result, rc, NULL);
}

static PyObject*
py_amount_parse(PyObject *self, PyObject *args, PyObject *kwds)
{
    int rc;
    char *s;
    char *default_currency = NULL;
    int with_expression = true;
    int auto_decimal_place = false;
    int strict_currency = false;
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

    Amount amount;
    bool res = amount_parse(
        &amount, s, default_currency, with_expression, auto_decimal_place,
        strict_currency);
    if (res) {
        PyMem_Free(s);
        return pyamount(&amount);
    } else {
        if (strict_currency) {
            Currency *c = amount_parse_currency(
                s, default_currency, strict_currency);
            if (c == NULL) {
                PyMem_Free(s);
                PyErr_SetString(UnsupportedCurrencyError, "no specified currency");
                return NULL;
            }
        }
        PyMem_Free(s);
        PyErr_SetString(PyExc_ValueError, "couldn't parse expression");
        return NULL;
    }
}

static PyObject*
py_amount_convert(PyObject *self, PyObject *args)
{
    PyObject *amount_p;
    char *code;
    PyObject *pydate;
    Amount dest;

    if (!PyArg_ParseTuple(args, "OsO", &amount_p, &code, &pydate)) {
        return NULL;
    }

    const Amount *amount = get_amount(amount_p);
    if (!amount->val) {
        Py_INCREF(amount_p);
        return amount_p;
    }
    dest.currency = getcur(code);
    if (dest.currency == NULL) {
        return NULL;
    }
    if (dest.currency == amount->currency) {
        Py_INCREF(amount_p);
        return amount_p;
    }
    time_t date = pydate2time(pydate);
    if (date == 1) {
        return NULL;
    }
    if (!amount_convert(&dest, amount, date)) {
        PyErr_SetString(PyExc_ValueError, "problems getting a rate");
        return NULL;
    }
    return pyamount(&dest);
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
    char *s = "";
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
    return pyamount(&res);
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
    return pyamount(&split->amount);
}

static int
PySplit_amount_set(PySplit *self, PyObject *value)
{
    const Amount *amount = get_amount(value);
    split_amount_set(self->split, amount);
    return 0;
}

static PyObject *
PySplit_account_name(PySplit *self)
{
    if (self->split->account == NULL) {
        return PyUnicode_InternFromString("");
    } else {
        return _strget(self->split->account->name);
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
        return pyamount(a);
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

static PyObject *
PySplit_is_new(PySplit *self)
{
    if (self->owned) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PySplit_index(PySplit *self)
{
    return PyLong_FromLong(self->split->index);
}

/* Split Methods */
static PySplit*
_PySplit_proxy(Split *split)
{
    PySplit *r = (PySplit *)PyType_GenericAlloc((PyTypeObject *)Split_Type, 0);
    r->owned = false;
    r->split = split;
    return r;
}

static int
PySplit_init(PySplit *self, PyObject *args, PyObject *kwds)
{
    PyObject *account, *amount_p;

    static char *kwlist[] = {"account", "amount", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OO", kwlist, &account, &amount_p);
    if (!res) {
        return -1;
    }

    self->split = malloc(sizeof(Split));
    self->owned = true;
    const Amount *amount = get_amount(amount_p);
    split_init(self->split, NULL, amount, 0);
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
PySplit_copy_from(PySplit *self, PyObject *other)
{
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

static Py_hash_t
PySplit_hash(PySplit *self)
{
    return (Py_hash_t)self->split;
}

static PyObject *
PySplit_richcompare(PySplit *a, PyObject *b, int op)
{
    if (!Split_Check(b)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if ((op == Py_EQ) || (op == Py_NE)) {
        bool match = a->split == ((PySplit *)b)->split;
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
PyTransaction_splits(PyTransaction *self)
{
    PyObject *res = PyList_New(self->txn.splitcount);
    for (unsigned int i=0; i<self->txn.splitcount; i++) {
        PySplit *split = _PySplit_proxy(&self->txn.splits[i]);
        PyList_SetItem(res, i, (PyObject *)split); // stolen
    }
    return res;
}

static PyObject *
PyTransaction_splits_set(PyTransaction *self, PyObject *value)
{
    Py_ssize_t len = PyList_Size(value);
    transaction_resize_splits(&self->txn, len);
    for (int i=0; i<len; i++) {
        PySplit *split = (PySplit *)PyList_GetItem(value, i); // borrowed
        split_copy(&self->txn.splits[i], split->split);
        self->txn.splits[i].index = i;
    }
    return 0;
}

static PyObject *
PyTransaction_amount(PyTransaction *self)
{
    Amount amount;
    if (transaction_amount(&self->txn, &amount)) {
        return pyamount(&amount);
    } else {
        return NULL;
    }
}

static PyObject *
PyTransaction_can_set_amount(PyTransaction *self)
{
    if (transaction_can_set_amount(&self->txn)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PyTransaction_has_unassigned_split(PyTransaction *self)
{
    for (unsigned int i=0; i<self->txn.splitcount; i++) {
        if (self->txn.splits[i].account == NULL) {
            Py_RETURN_TRUE;
        }
    }
    Py_RETURN_FALSE;
}

static PyObject *
PyTransaction_is_mct(PyTransaction *self)
{
    if (transaction_is_mct(&self->txn)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PyTransaction_is_null(PyTransaction *self)
{
    if (transaction_is_null(&self->txn)) {
        Py_RETURN_TRUE;
    } else {
        Py_RETURN_FALSE;
    }
}

static PyObject *
PyTransaction_amount_for_account(PyTransaction *self, PyObject *args)
{
    PyObject *account_p;
    char *code;
    if (!PyArg_ParseTuple(args, "Os", &account_p, &code)) {
        return NULL;
    }
    Account *account = NULL;
    if (account_p != Py_None) {
        account = ((PyAccount *)account_p)->account;
    }
    Amount a;
    a.currency = getcur(code);
    if (a.currency == NULL) {
        return NULL;
    }
    transaction_amount_for_account(&self->txn, &a, account);
    return pyamount(&a);
}

static PyObject *
PyTransaction_affected_accounts(PyTransaction *self, PyObject *args)
{
    Account **accounts = transaction_affected_accounts(&self->txn);
    PyObject *res = PySet_New(NULL);
    while (*accounts != NULL) {
        PyAccount *a = _PyAccount_from_account(*accounts);
        PySet_Add(res, (PyObject*)a);
        Py_DECREF(a);
        accounts++;
    }
    return res;
}

static PyObject *
PyTransaction_add_split(PyTransaction *self, PySplit *split)
{
    transaction_resize_splits(&self->txn, self->txn.splitcount+1);
    Split *newsplit = &self->txn.splits[self->txn.splitcount-1];
    split_copy(newsplit, split->split);
    newsplit->index = self->txn.splitcount-1;
    return (PyObject *)_PySplit_proxy(newsplit);
}

static PyObject *
PyTransaction_assign_imbalance(PyTransaction *self, PySplit *target_split)
{
    transaction_assign_imbalance(&self->txn, target_split->split);
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_balance(PyTransaction *self, PyObject *args)
{
    PyObject *strong_split_p = NULL;
    Split *strong_split;
    int keep_two_splits = false;

    if (!PyArg_ParseTuple(args, "|Op", &strong_split_p, &keep_two_splits)) {
        return NULL;
    }
    if (strong_split_p == NULL || strong_split_p == Py_None) {
        strong_split = NULL;
    } else if (!Split_Check(strong_split_p)) {
        PyErr_SetString(PyExc_TypeError, "not a split");
        return NULL;
    } else {
        strong_split = ((PySplit *)strong_split_p)->split;
    }
    transaction_balance(&self->txn, strong_split, keep_two_splits);
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_copy_from(PyTransaction *self, PyTransaction *other)
{
    if (!PyObject_IsInstance((PyObject *)other, Transaction_Type)) {
        PyErr_SetString(PyExc_TypeError, "not a txn");
        return NULL;
    }
    if (!transaction_copy(&self->txn, &other->txn)) {
        PyErr_SetString(PyExc_RuntimeError, "low level copy failed");
        return NULL;
    }
    Py_RETURN_NONE;
}

/* Changes our transaction and do all proper stuff.
 *
 * Sets all specified arguments to their specified values and do proper
 * adjustments, such as making sure that our `Split.reconciliation_date`
 * still make sense and updates our `mtime`.
 *
 * Moreover, it offers a convenient interface to specify a two-way transaction
 * with `from_`, `to` and `amount`. When those are set, we'll set up splits
 * corresponding to this two-way money movement.
 *
 * If `currency` is set, it changes the currency of the amounts in all `splits`,
 * without conversion with exchange rates. Amounts are kept intact.
 */
static PyObject*
PyTransaction_change(PyTransaction *self, PyObject *args, PyObject *kwds)
{
    PyObject *date_p = NULL;
    PyObject *description = NULL;
    PyObject *payee = NULL;
    PyObject *checkno = NULL;
    PyObject *notes = NULL;
    PyAccount *from_p = NULL;
    PyAccount *to_p = NULL;
    PyObject *amount_p = NULL;
    PyObject *splits = NULL;
    char *currency_code = NULL;
    static char *kwlist[] = {"date", "description", "payee", "checkno", "from_",
        "to", "amount", "currency", "notes", "splits", NULL};

    int res = PyArg_ParseTupleAndKeywords(args, kwds, "|OOOOOOOzOO", kwlist,
        &date_p, &description, &payee, &checkno, &from_p, &to_p, &amount_p,
        &currency_code, &notes, &splits);
    if (!res) {
        return NULL;
    }

    Transaction *txn = &self->txn;
    Account *from = NULL;
    if (from_p != NULL && (PyObject *)from_p != Py_None) {
        from = from_p->account;
    }
    Account *to = NULL;
    if (to_p != NULL && (PyObject *)to_p != Py_None) {
        to = to_p->account;
    }
    const Amount *amount = NULL;
    if (amount_p != NULL) {
        amount = get_amount(amount_p);
    }
    Currency *currency = NULL;
    if (currency_code != NULL) {
        currency = getcur(currency_code);
        if (currency == NULL) {
            return NULL;
        }
    }
    if (date_p != NULL) {
        time_t date = pydate2time(date_p);
        if (date == 1) {
            return NULL;
        }
        bool future = date > today();
        for (unsigned int i=0; i<txn->splitcount; i++) {
            Split *s = &txn->splits[i];
            if (future) {
                s->reconciliation_date = 0;
            } else if (s->reconciliation_date == txn->date) {
                // When txn/split dates are in sync, we keep them in sync.
                s->reconciliation_date = date;
            }
        }
        txn->date = date;
    }
    if (description != NULL) {
        _strset(&txn->description, description);
    }
    if (payee != NULL) {
        _strset(&txn->payee, payee);
    }
    if (checkno != NULL) {
        _strset(&txn->checkno, checkno);
    }
    if (notes != NULL) {
        _strset(&txn->notes, notes);
    }
    if (amount != NULL && from_p != NULL && to_p != NULL && txn->splitcount == 0) {
        // special case: we're wanting to setup a new two-way txn.
        transaction_resize_splits(txn, 2);
        txn->splits[0].account = from;
        amount_copy(&txn->splits[0].amount, amount);
        txn->splits[1].account = to;
        amount_neg(&txn->splits[1].amount, amount);
        amount = NULL;
        from = to = NULL;
        from_p = to_p = NULL;
    }
    if (amount != NULL && txn->splitcount == 2 && !transaction_is_mct(txn)) {
        Amount *first = &txn->splits[0].amount;
        Amount *second = &txn->splits[1].amount;
        if ((first->val > 0) == (amount->val > 0)) {
            amount_copy(first, amount);
            amount_neg(second, amount);
        } else {
            amount_neg(first, amount);
            amount_copy(second, amount);
        }
    }
    if (from_p != NULL || to_p != NULL) {
        Split *found_from = NULL;
        Split *found_to = NULL;
        bool multiple_from = false;
        bool multiple_to = false;
        for (unsigned int i=0; i<txn->splitcount; i++) {
            Split *s = &txn->splits[i];
            if (s->amount.val == 0) {
                // could be either a to or a from. The rules below come from
                // the old python implementation: When we have multiple null
                // splits, "to" gets the last of them all the time. If there are
                // more than 2, "from" gets none of them (can't have multiple
                // splits in from/to assignment targets), but "to" still gets
                // the last one. When we mix null and not-null splits on the
                // "to" side, however, then we can get in a "multiple_to"
                // situation.
                if (found_from == NULL) {
                    found_from = s;
                } else if (found_to == NULL) {
                    found_to = s;
                } else {
                    multiple_from = true;
                    if (found_to->amount.val == 0) {
                        found_to = s;
                    } else {
                        multiple_to = true;
                    }
                }
            }
            else if (txn->splits[i].amount.val <= 0) {
                if (found_from == NULL) {
                    found_from = s;
                } else {
                    multiple_from = true;
                }
            } else {
                if (found_to == NULL) {
                    found_to = s;
                } else {
                    multiple_to = true;
                }
            }
        }
        if (found_from != NULL && from_p != NULL && !multiple_from) {
            split_account_set(found_from, from);
        }
        if (found_to != NULL && to_p != NULL && !multiple_to) {
            split_account_set(found_to, to);
        }
    }
    if (currency != NULL) {
        for (unsigned int i=0; i<txn->splitcount; i++) {
            Split *s = &txn->splits[i];
            if (s->amount.currency != NULL && s->amount.currency != currency) {
                s->amount.currency = currency;
                s->reconciliation_date = 0;
            }
        }
        transaction_balance(txn, NULL, false);
    }
    if (splits != NULL) {
        PyTransaction_splits_set(self, splits);
    }
    // Reconciliation can never be lower than txn date
    for (unsigned int i=0; i<txn->splitcount; i++) {
        Split *s = &txn->splits[i];
        if (s->reconciliation_date > 0 && s->reconciliation_date < txn->date) {
            s->reconciliation_date = txn->date;
        }
    }
    txn->mtime = now();
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_mct_balance(PyTransaction *self, PyObject *args)
{
    char *new_split_currency_code;

    if (!PyArg_ParseTuple(args, "s", &new_split_currency_code)) {
        return NULL;
    }
    Currency *new_split_currency = getcur(new_split_currency_code);
    if (new_split_currency == NULL) {
        return NULL;
    }
    transaction_mct_balance(&self->txn, new_split_currency);
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_move_split(PyTransaction *self, PyObject *args)
{
    PySplit *split;
    int index;

    if (!PyArg_ParseTuple(args, "Oi", &split, &index)) {
        return NULL;
    }
    if (!transaction_move_split(&self->txn, split->split, index)) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_reassign_account(PyTransaction *self, PyObject *args)
{
    PyAccount *account_p, *reassign_to_p = NULL;

    if (!PyArg_ParseTuple(args, "O|O", &account_p, &reassign_to_p)) {
        return NULL;
    }
    Account *account = account_p->account;
    Account *reassign_to = NULL;
    if (reassign_to_p != NULL && (PyObject *)reassign_to_p != Py_None) {
        reassign_to = reassign_to_p->account;
    }
    transaction_reassign_account(&self->txn, account, reassign_to);
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_remove_split(PyTransaction *self, PySplit *split)
{
    if (!transaction_remove_split(&self->txn, split->split)) {
        return NULL;
    }
    transaction_balance(&self->txn, NULL, false);
    Py_RETURN_NONE;
}

static PyObject *
PyTransaction_replicate(PyTransaction *self, PyObject *noarg)
{
    PyTransaction *res = (PyTransaction *)PyType_GenericAlloc((PyTypeObject *)Transaction_Type, 0);
    PyTransaction_copy_from(res, self);
    return (PyObject *)res;
}

static PyObject *
PyTransaction_repr(PyTransaction *self)
{
    PyObject *tdate = PyTransaction_date(self);
    if (tdate == NULL) {
        return NULL;
    }
    return PyUnicode_FromFormat(
        "Transaction(%d %S %s)", self->txn.type, tdate, self->txn.description);
}

static int
PyTransaction_init(PyTransaction *self, PyObject *args, PyObject *kwds)
{
    PyObject *date_p, *description, *payee, *checkno, *account_p, *amount_p;
    int txntype;

    static char *kwlist[] = {"type", "date", "description", "payee", "checkno",
        "account", "amount", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "iOOOOOO", kwlist, &txntype, &date_p, &description, &payee,
        &checkno, &account_p, &amount_p);
    if (!res) {
        return -1;
    }

    time_t date = pydate2time(date_p);
    if (date == 1) {
        return -1;
    }
    transaction_init(&self->txn, txntype, date);
    PyTransaction_description_set(self, description);
    PyTransaction_payee_set(self, payee);
    PyTransaction_checkno_set(self, checkno);
    if (amount_p != Py_None) {
        transaction_resize_splits(&self->txn, 2);
        Split *s1 = &self->txn.splits[0];
        Split *s2 = &self->txn.splits[1];
        if (account_p != Py_None) {
            s1->account = ((PyAccount *)account_p)->account;
        }
        const Amount *amount = get_amount(amount_p);
        amount_copy(&s1->amount, amount);
        amount_copy(&s2->amount, amount);
        s2->amount.val *= -1;
    }
    return 0;
}

static void
PyTransaction_dealloc(PyTransaction *self)
{
    transaction_deinit(&self->txn);
}

/* Entry Methods */
static int
PyEntry_init(PyEntry *self, PyObject *args, PyObject *kwds)
{
    PySplit *split_p;
    static char *kwlist[] = {"split", "transaction", NULL};

    int res = PyArg_ParseTupleAndKeywords(
        args, kwds, "OO", kwlist, &split_p, &self->txn);
    if (!res) {
        return -1;
    }
    if (!Split_Check(split_p)) {
        PyErr_SetString(PyExc_TypeError, "not a split");
        return -1;
    }
    if (!PyObject_IsInstance((PyObject *)self->txn, Transaction_Type)) {
        PyErr_SetString(PyExc_TypeError, "not a txn");
        return -1;
    }
    Py_INCREF(self->txn);
    entry_init(&self->entry, split_p->split, &self->txn->txn);
    return 0;
}

static PyObject *
PyEntry_account(PyEntry *self)
{
    Split *split = self->entry.split;
    if (split->account == NULL) {
        Py_RETURN_NONE;
    } else {
        return (PyObject *)_PyAccount_from_account(split->account);
    }
}

static PyObject *
PyEntry_amount(PyEntry *self)
{
    return pyamount(&self->entry.split->amount);
}

static PyObject *
PyEntry_balance(PyEntry *self)
{
    return pyamount(&self->entry.balance);
}

static PyObject *
PyEntry_balance_with_budget(PyEntry *self)
{
    return pyamount(&self->entry.balance_with_budget);
}

static PyObject *
PyEntry_checkno(PyEntry *self)
{
    return PyTransaction_checkno(self->txn);
}

static PyObject *
PyEntry_date(PyEntry *self)
{
    return PyTransaction_date(self->txn);
}

static PyObject *
PyEntry_description(PyEntry *self)
{
    return PyTransaction_description(self->txn);
}

static PyObject *
PyEntry_payee(PyEntry *self)
{
    return PyTransaction_payee(self->txn);
}

static PyObject *
PyEntry_mtime(PyEntry *self)
{
    return PyTransaction_mtime(self->txn);
}

static PyObject *
PyEntry_reconciled(PyEntry *self)
{
    if (self->entry.split->reconciliation_date == 0) {
        Py_RETURN_FALSE;
    } else {
        Py_RETURN_TRUE;
    }
}

static PyObject *
PyEntry_reconciled_balance(PyEntry *self)
{
    return pyamount(&self->entry.reconciled_balance);
}

static PyObject *
PyEntry_reconciliation_date(PyEntry *self)
{
    return time2pydate(self->entry.split->reconciliation_date);
}

static PyObject *
PyEntry_reference(PyEntry *self)
{
    return _strget(self->entry.split->reference);
}

static PyObject *
PyEntry_split(PyEntry *self)
{
    return (PyObject *)_PySplit_proxy(self->entry.split);
}

static PyObject *
PyEntry_splits(PyEntry *self)
{
    PyObject *res = PyList_New(self->entry.txn->splitcount - 1);
    int j = 0;
    for (unsigned int i=0; i<self->entry.txn->splitcount; i++) {
        if (i == self->entry.split->index) {
            continue;
        }
        PySplit *split = _PySplit_proxy(&self->entry.txn->splits[i]);
        PyList_SetItem(res, j, (PyObject *)split); // stolen
        j++;
    }
    return res;
}

static PyObject *
PyEntry_transaction(PyEntry *self)
{
    Py_INCREF(self->txn);
    return (PyObject *)self->txn;
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

static PyObject*
PyEntry_change_amount(PyEntry *self, PyObject *amount)
{
    if (!entry_amount_set(&self->entry, get_amount(amount))) {
        PyErr_SetString(PyExc_ValueError, "not a two-way txn");
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject*
PyEntry_normal_balance(PyEntry *self, PyObject *args)
{
    Amount amount;
    amount_copy(&amount, &self->entry.balance);
    Account *a = self->entry.split->account;
    if (a != NULL) {
        if (account_is_credit(a)) {
            amount.val *= -1;
        }
    }
    return pyamount(&amount);
}

static PyObject *
PyEntry_richcompare(PyEntry *a, PyObject *b, int op)
{
    if (!Entry_Check(b)) {
        Py_RETURN_NOTIMPLEMENTED;
    }
    if (op == Py_EQ) {
        if (a->entry.split == ((PyEntry *)b)->entry.split) {
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
    return (Py_hash_t)self->entry.split;
}

static PyObject *
PyEntry_repr(PyEntry *self)
{
    PyObject *tdate = PyTransaction_date(self->txn);
    if (tdate == NULL) {
        return NULL;
    }
    return PyUnicode_FromFormat(
        "Entry(%S %s)", tdate, self->txn->txn.description);
}

static void
PyEntry_dealloc(PyEntry *self)
{
    Py_DECREF(self->txn);
}

/* EntryList */
static PyEntryList*
_PyEntryList_new(Account *account)
{
    PyEntryList *res = (PyEntryList *)PyType_GenericAlloc((PyTypeObject *)EntryList_Type, 0);
    res->account = account;
    res->entries = PyList_New(0);
    res->last_reconciled = NULL;
    res->tmplist.count = 0;
    res->tmplist.entries = NULL;
    return res;
}

static EntryList*
_PyEntryList_entries(PyEntryList *self)
{
    if (self->tmplist.entries != NULL) {
        free(self->tmplist.entries);
    }
    Py_ssize_t len = PyList_Size(self->entries);
    self->tmplist.count = len;
    self->tmplist.entries = malloc(sizeof(Entry *) * len);
    for (int i=0; i<len; i++) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(self->entries, i); // borrowed
        self->tmplist.entries[i] = &entry->entry;
    }
    self->tmplist.last_reconciled = self->last_reconciled;
    return &self->tmplist;
}

static void
_PyEntryList_maybe_set_last_reconciled(PyEntryList *self, Entry *entry)
{
    if (entry->split->reconciliation_date != 0) {
        if (self->last_reconciled == NULL) {
            self->last_reconciled = entry;
        } else {
            bool replace = false;
            Entry *old = self->last_reconciled;
            if (entry->split->reconciliation_date != old->split->reconciliation_date) {
                if (entry->split->reconciliation_date > old->split->reconciliation_date) {
                    replace = true;
                }
            } else if (entry->txn->date != old->txn->date) {
                if (entry->txn->date > old->txn->date) {
                    replace = true;
                }
            } else if (entry->txn->position != old->txn->position) {
                if (entry->txn->position > old->txn->position) {
                    replace = true;
                }
            } else if (entry->index > old->index) {
                replace = true;
            }
            if (replace) {
                self ->last_reconciled = entry;
            }
        }
    }
}

static void
_PyEntryList_add_entry(PyEntryList *self, PyEntry *entry)
{
    PyList_Append(self->entries, (PyObject *)entry);
    _PyEntryList_maybe_set_last_reconciled(self, &entry->entry);
}

static PyObject*
PyEntryList_last_entry(PyEntryList *self, PyObject *args)
{
    PyObject *date_p;

    if (!PyArg_ParseTuple(args, "O", &date_p)) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(self->entries);
    if (!len) {
        Py_RETURN_NONE;
    }
    int index;
    if (date_p == Py_None) {
        index = len;
    } else {
        time_t date = pydate2time(date_p);
        if (date == 1) {
            return NULL;
        }
        EntryList *el = _PyEntryList_entries(self);
        index = entries_find_date(el, date, true);
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
    PyObject *date_p;

    if (!PyArg_ParseTuple(args, "O", &date_p)) {
        return NULL;
    }
    Py_ssize_t len = PyList_Size(self->entries);
    int index;
    if (date_p == Py_None) {
        index = 0;
    } else {
        time_t date = pydate2time(date_p);
        if (date == 1) {
            return NULL;
        }
        EntryList *el = _PyEntryList_entries(self);
        index = entries_find_date(el, date, false);
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
            self, &((PyEntry *)PyList_GetItem(self->entries, i))->entry);
    }
    Py_RETURN_NONE;
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
    time_t date = pydate2time(date_p);
    if (date == 1) {
        return NULL;
    }
    EntryList *el = _PyEntryList_entries(self);
    if (!entries_balance(el, &dst, date, with_budget)) {
        return NULL;
    } else {
        return pyamount(&dst);
    }
}

static bool
_PyEntryList_cash_flow(PyEntryList *self, Amount *dst, PyObject *daterange)
{
    dst->val = 0;
    Py_ssize_t len = PyList_Size(self->entries);
    for (int i=0; i<len; i++) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(self->entries, i); // borrowed
        if (entry->txn->txn.type == TXN_TYPE_BUDGET) {
            continue;
        }
        PyObject *date_p = PyEntry_date(entry);
        if (date_p == NULL) {
            return false;
        }
        if (PySequence_Contains(daterange, date_p)) {
            Amount a;
            a.currency = dst->currency;
            Amount *src = &entry->entry.split->amount;
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
    return pyamount(&res);
}

static PyObject*
PyEntryList_normal_balance(PyEntryList *self, PyObject *args)
{
    PyObject *date_p = Py_None;
    char *currency = NULL;

    if (!PyArg_ParseTuple(args, "|Os", &date_p, &currency)) {
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
    time_t date = pydate2time(date_p);
    if (date == 1) {
        return NULL;
    }
    EntryList *el = _PyEntryList_entries(self);
    if (!entries_balance(el, &res, date, false)) {
        return NULL;
    } else {
        account_normalize_amount(self->account, &res);
        return pyamount(&res);
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
        return pyamount(&res);
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
    if (self->tmplist.entries != NULL) {
        free(self->tmplist.entries);
    }
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

/* Oven functions */

static bool
_py_oven_cook_splits(
    PyObject *splitpairs, PyEntryList *entries)
{
    Py_ssize_t len = PySequence_Length(splitpairs);
    PyObject *newentries = PyList_New(len);
    EntryList tocook;
    tocook.count = len;
    tocook.entries = malloc(sizeof(Entry *) * len);
    for (int i=0; i<len; i++) {
        PyObject *item = PySequence_GetItem(splitpairs, i);
        PyEntry *entry = (PyEntry *)PyType_GenericAlloc((PyTypeObject *)Entry_Type, 0);
        entry->txn = (PyTransaction *)PyTuple_GetItem(item, 0); // borrowed
        if (entry->txn == NULL) {
            Py_DECREF(item);
            Py_DECREF(entry);
            Py_DECREF(newentries);
            return false;
        }
        PySplit *split_p = (PySplit *)PyTuple_GetItem(item, 1); // borrowed
        if (split_p == NULL) {
            Py_DECREF(item);
            Py_DECREF(entry);
            Py_DECREF(newentries);
            return NULL;
        }
        Py_INCREF(entry->txn);
        entry_init(&entry->entry, split_p->split, &entry->txn->txn);
        tocook.entries[i] = &entry->entry;
        PyList_SetItem(newentries, i, (PyObject *)entry); // stolen
    }
    EntryList *ref = _PyEntryList_entries(entries);
    entries_cook(ref, &tocook, entries->account->currency);
    free(tocook.entries);
    for (int i=0; i<len; i++) {
        PyEntry *entry = (PyEntry *)PyList_GetItem(newentries, i); // borrowed
        _PyEntryList_add_entry(entries, entry);
    }
    Py_DECREF(newentries);
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
        PyTransaction *txn = (PyTransaction *)PyList_GetItem(txns, i); // borrowed
        int slen = txn->txn.splitcount;
        for (int j=0; j<slen; j++) {
            Split *split = &txn->txn.splits[j];
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
            PySplit *split_p = _PySplit_proxy(split);
            PyObject *pair = PyTuple_Pack(2, txn, split_p);
            Py_DECREF(split_p);
            PyList_Append(splitpairs, pair);
            Py_DECREF(pair);
        }
    }

    Py_ssize_t pos = 0;
    PyObject *k, *v;
    while (PyDict_Next(a2s, &pos, &k, &v)) {
        const char *aname = PyUnicode_AsUTF8(k);
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

static PyObject*
py_patch_today(PyObject *self, PyObject *today_p)
{
    if (today_p == Py_None) {
        // unpatch
        today_patch(0);
    } else {
        time_t today = pydate2time(today_p);
        if (today == 1) {
            return NULL;
        }
        today_patch(today);
    }
    Py_RETURN_NONE;
}

/* PyTransactionList */

static int
PyTransactionList_init(PyTransactionList *self, PyObject *args, PyObject *kwds)
{
    static char *kwlist[] = {NULL};

    int res = PyArg_ParseTupleAndKeywords(args, kwds, "", kwlist);
    if (!res) {
        return -1;
    }

    self->txns = PyList_New(0);
    return 0;
}

static PyObject*
PyTransactionList_add(PyTransactionList *self, PyObject *args)
{
    PyTransaction *txn;
    int keep_position = false;
    int position = -1;

    if (!PyArg_ParseTuple(args, "O|pi", &txn, &keep_position, &position)) {
        return NULL;
    }
    if (!PyObject_IsInstance((PyObject *)txn, Transaction_Type)) {
        PyErr_SetString(PyExc_TypeError, "not a txn");
        return NULL;
    }
    PyList_Append(self->txns, (PyObject *)txn);
    Py_RETURN_NONE;
}

static PyObject*
PyTransactionList_clear(PyTransactionList *self, PyObject *args)
{
    Py_ssize_t len = PyList_Size(self->txns);
    if (PyList_SetSlice(self->txns, 0, len, NULL) == -1) {
        return NULL;
    }
    Py_RETURN_NONE;
}

static PyObject*
PyTransactionList_first(PyTransactionList *self, PyObject *args)
{
    PyObject *res = PyList_GetItem(self->txns, 0); // borrowed
    Py_INCREF(res);
    return res;
}

static PyObject*
PyTransactionList_last(PyTransactionList *self, PyObject *args)
{
    Py_ssize_t len = PyList_Size(self->txns);
    PyObject *res = PyList_GetItem(self->txns, len - 1); // borrowed
    Py_INCREF(res);
    return res;
}

static PyObject*
PyTransactionList_remove(PyTransactionList *self, PyObject *txn)
{
    return PyObject_CallMethod(self->txns, "remove", "O", txn);
}

static PyObject*
PyTransactionList_sort(PyTransactionList *self, PyObject *args)
{
    Py_ssize_t len = PyList_Size(self->txns);
    PyObject *sorter = PyList_New(len);
    for (int i=0; i<len; i++) {
        PyTransaction *txn = (PyTransaction *)PyList_GetItem(self->txns, i); // borrowed
        PyObject *date = PyTransaction_date(txn);
        PyObject *position = PyTransaction_position(txn);
        PyObject *t = PyTuple_Pack(3, date, position, (PyObject *)txn);
        Py_DECREF(date);
        Py_DECREF(position);
        PyList_SetItem(sorter, i, t); // stolen
    }
    PyList_Sort(sorter);
    for (int i=0; i<len; i++) {
        PyObject *t = PyList_GetItem(sorter, i); // borrowed
        PyObject *txn = PyTuple_GetItem(t, 2); // borrowed
        Py_INCREF(txn);
        PyList_SetItem(self->txns, i, txn); // stolen
    }
    Py_DECREF(sorter);
    Py_RETURN_NONE;
}

static PyObject*
PyTransactionList_iter(PyTransactionList *self)
{
    return PyObject_GetIter(self->txns);
}

static Py_ssize_t
PyTransactionList_len(PyTransactionList *self)
{
    return PyList_Size(self->txns);
}

static void
PyTransactionList_dealloc(PyTransactionList *self)
{
    Py_DECREF(self->txns);
}

/* Python Boilerplate */

static PyGetSetDef PyAmount_getseters[] = {
    {"currency_code", (getter)PyAmount_getcurrency_code, NULL, "currency_code", NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Amount_Slots[] = {
    {Py_tp_repr, PyAmount_repr},
    {Py_tp_hash, PyAmount_hash},
    {Py_tp_richcompare, PyAmount_richcompare},
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
    {"copy_from", (PyCFunction)PySplit_copy_from, METH_O, ""},
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

    // Whether out split is part of a txn or a new split being created.
    {"is_new", (getter)PySplit_is_new, NULL, NULL, NULL},
    // index within its parent txn
    {"index", (getter)PySplit_index, NULL, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Split_Slots[] = {
    {Py_tp_init, PySplit_init},
    {Py_tp_methods, PySplit_methods},
    {Py_tp_getset, PySplit_getseters},
    {Py_tp_repr, PySplit_repr},
    {Py_tp_richcompare, PySplit_richcompare},
    {Py_tp_hash, PySplit_hash},
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
    {"change_amount", (PyCFunction)PyEntry_change_amount, METH_O, ""},
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
    {"split", (getter)PyEntry_split, NULL, NULL, NULL},
    {"splits", (getter)PyEntry_splits, NULL, NULL, NULL},
    {"transaction", (getter)PyEntry_transaction, NULL, NULL, NULL},
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
    {"patch_today", py_patch_today, METH_O},
    {NULL}  /* Sentinel */
};

static PyMethodDef PyEntryList_methods[] = {
    // Returns running balance at `date`.
    // If `currency` is specified, the result is converted to it.
    // if `with_budget` is True, budget spawns are counted.
    {"balance", (PyCFunction)PyEntryList_balance, METH_VARARGS, ""},
    // Returns the sum of entry amounts occuring in `date_range`.
    // If `currency` is specified, the result is converted to it.
    {"cash_flow", (PyCFunction)PyEntryList_cash_flow, METH_VARARGS, ""},
    // Remove all entries after `from_date`.
    {"clear", (PyCFunction)PyEntryList_clear, METH_VARARGS, ""},
    // Return the last entry with a date that isn't after `date`.
    // If `date` isn't specified, returns the last entry in the list.
    {"last_entry", (PyCFunction)PyEntryList_last_entry, METH_VARARGS, ""},
    {"normal_balance", (PyCFunction)PyEntryList_normal_balance, METH_VARARGS, ""},
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
    {"amount_for_account", (PyCFunction)PyTransaction_amount_for_account, METH_VARARGS, ""},
    {"add_split", (PyCFunction)PyTransaction_add_split, METH_O, ""},
    {"affected_accounts", (PyCFunction)PyTransaction_affected_accounts, METH_NOARGS, ""},
    {"assign_imbalance", (PyCFunction)PyTransaction_assign_imbalance, METH_O, ""},
    {"balance", (PyCFunction)PyTransaction_balance, METH_VARARGS, ""},
    {"change", (PyCFunction)PyTransaction_change, METH_VARARGS|METH_KEYWORDS, ""},
    {"copy_from", (PyCFunction)PyTransaction_copy_from, METH_O, ""},
    {"mct_balance", (PyCFunction)PyTransaction_mct_balance, METH_VARARGS, ""},
    {"move_split", (PyCFunction)PyTransaction_move_split, METH_VARARGS, ""},
    {"reassign_account", (PyCFunction)PyTransaction_reassign_account, METH_VARARGS, ""},
    {"remove_split", (PyCFunction)PyTransaction_remove_split, METH_O, ""},
    {"replicate", (PyCFunction)PyTransaction_replicate, METH_NOARGS, ""},
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
    {"splits", (getter)PyTransaction_splits, (setter)PyTransaction_splits_set, NULL, NULL},
    {"amount", (getter)PyTransaction_amount, NULL, NULL, NULL},
    {"can_set_amount", (getter)PyTransaction_can_set_amount, NULL, NULL, NULL},
    {"has_unassigned_split", (getter)PyTransaction_has_unassigned_split, NULL, NULL, NULL},
    {"is_mct", (getter)PyTransaction_is_mct, NULL, NULL, NULL},
    {"is_null", (getter)PyTransaction_is_null, NULL, NULL, NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Transaction_Slots[] = {
    {Py_tp_init, PyTransaction_init},
    {Py_tp_methods, PyTransaction_methods},
    {Py_tp_getset, PyTransaction_getseters},
    {Py_tp_repr, PyTransaction_repr},
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

static PyMethodDef PyTransactionList_methods[] = {
    {"add", (PyCFunction)PyTransactionList_add, METH_VARARGS, ""},
    {"clear", (PyCFunction)PyTransactionList_clear, METH_NOARGS, ""},
    {"first", (PyCFunction)PyTransactionList_first, METH_NOARGS, ""},
    {"last", (PyCFunction)PyTransactionList_last, METH_NOARGS, ""},
    {"remove", (PyCFunction)PyTransactionList_remove, METH_O, ""},
    {"sort", (PyCFunction)PyTransactionList_sort, METH_NOARGS, ""},
    {0, 0, 0, 0},
};

static PyType_Slot TransactionList_Slots[] = {
    {Py_tp_init, PyTransactionList_init},
    {Py_tp_methods, PyTransactionList_methods},
    {Py_sq_length, PyTransactionList_len},
    {Py_tp_iter, PyTransactionList_iter},
    {Py_tp_dealloc, PyTransactionList_dealloc},
    {0, 0},
};

PyType_Spec TransactionList_Type_Spec = {
    "_ccore.TransactionList",
    sizeof(PyTransactionList),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    TransactionList_Slots,
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

    TransactionList_Type = PyType_FromSpec(&TransactionList_Type_Spec);
    PyModule_AddObject(m, "TransactionList", TransactionList_Type);
    return m;
}
