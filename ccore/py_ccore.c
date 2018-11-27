#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "amount.h"

/* Types */
static PyObject *UnsupportedCurrencyError = NULL;

typedef struct {
    PyObject_HEAD
    Amount amount;
    PyObject *rval; /* Real value, as a python float instance */
} PyAmount;

static PyObject *Amount_Type;

#define Amount_Check(v) (Py_TYPE(v) == (PyTypeObject *)Amount_Type)

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

static PyObject *
create_amount(int64_t ival, Currency *currency)
{
    /* Create a new amount in a way that is faster than the normal init */
    PyAmount *r;
    double dtmp;

    r = (PyAmount *)PyType_GenericAlloc((PyTypeObject *)Amount_Type, 0);
    r->amount.val = ival;
    r->amount.currency = currency;
    dtmp = (double)ival / pow(10, r->amount.currency->exponent);
    r->rval = PyFloat_FromDouble(dtmp);
    if (r->rval == NULL) {
        return NULL;
    }
    return (PyObject *)r;
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

static void
PyAmount_dealloc(PyAmount *self)
{
    Py_XDECREF(self->rval);
    PyObject_Del(self);
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
    self->rval = PyFloat_FromDouble(0);
    if (self->rval == NULL) {
        Py_DECREF(self);
        return NULL;
    }

    return (PyObject *)self;
}

static int
PyAmount_init(PyAmount *self, PyObject *args, PyObject *kwds)
{
    PyObject *amount, *tmp;
    const char *code;
    double dtmp;
    Currency *c;

    static char *kwlist[] = {"amount", "currency", NULL};

    self->rval = NULL;

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
    tmp = self->rval;
    Py_INCREF(amount);
    self->rval = amount;
    Py_XDECREF(tmp);
    return 0;
}

static int
PyAmount_traverse(PyAmount *self, visitproc visit, void *arg)
{
    Py_VISIT(self->rval);
    return 0;
}

static int
PyAmount_clear(PyAmount *self)
{
    Py_CLEAR(self->rval);
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
        "(iOs)", self->amount.val, self->rval, self->amount.currency->code);
    fmt = PyUnicode_FromString("Amount(%r, %r, %r)");
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
    return PyNumber_Float(self->rval);
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
        return PyNumber_TrueDivide(((PyAmount *)a)->rval, ((PyAmount *)b)->rval);
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

static PyObject *
PyAmount_getvalue(PyAmount *self)
{
    Py_INCREF(self->rval);
    return self->rval;
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
    double dtmp;
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
    Currency *currency;
    double rate;

    if (!PyArg_ParseTuple(args, "OsO", &pyamount, &code, &pydate)) {
        return NULL;
    }

    amount = get_amount(pyamount);
    if (!amount->val) {
        Py_INCREF(pyamount);
        return pyamount;
    }
    currency = getcur(code);
    if (currency == NULL) {
        return NULL;
    }
    if (currency == amount->currency) {
        Py_INCREF(pyamount);
        return pyamount;
    }
    if (!pydate2tm(pydate, &date)) {
        return NULL;
    }
    if (currency_getrate(&date, amount->currency, currency, &rate) != CURRENCY_OK) {
        PyErr_SetString(PyExc_ValueError, "problems getting a rate");
        return NULL;
    }
    int64_t res = amount_slide(
        amount->val * rate,
        amount->currency->exponent,
        currency->exponent);
    return create_amount(res, currency);
}

/* We need both __copy__ and __deepcopy__ methods for amounts to behave
 * correctly in undo_test. */
static PyMethodDef PyAmount_methods[] = {
    {"__copy__", (PyCFunction)PyAmount_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PyAmount_deepcopy, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyAmount_getseters[] = {
    {"currency_code", (getter)PyAmount_getcurrency_code, NULL, "currency_code", NULL},
    {"value", (getter)PyAmount_getvalue, NULL, "value", NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Amount_Slots[] = {
    {Py_tp_new, PyAmount_new},
    {Py_tp_init, PyAmount_init},
    {Py_tp_dealloc, PyAmount_dealloc},
    {Py_tp_repr, PyAmount_repr},
    {Py_tp_hash, PyAmount_hash},
    {Py_tp_traverse, PyAmount_traverse},
    {Py_tp_clear, PyAmount_clear},
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

    Amount_Type = PyType_FromSpec(&Amount_Type_Spec);

    m = PyModule_Create(&CCoreDef);
    if (m == NULL) {
        return NULL;
    }

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
    return m;
}

