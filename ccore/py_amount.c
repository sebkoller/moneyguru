#include <Python.h>
#include <math.h>
#include "amount.h"

typedef struct {
    PyObject_HEAD
    Amount amount;
    PyObject *rval; /* Real value, as a python float instance */
} PyAmount;

PyObject *Amount_Type;

#define Amount_Check(v) (Py_TYPE(v) == (PyTypeObject *)Amount_Type)

/* Utility funcs */

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
    int exponent;

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

/* Methods */

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
    char *code;
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
    PyObject *currency;

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
    PyObject *currency;

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

/* Functions */
PyObject*
py_amount_format(PyObject *self, PyObject *args, PyObject *kwds)
{
    int rc;
    Amount *amount;
    PyObject *pyamount;
    char *default_currency = "";
    char *zero_currency = "";
    bool blank_zero = false;
    bool show_currency = false;
    char *decimal_sep = ".";
    char *grouping_sep = "";
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

PyObject*
py_amount_parse_single(PyObject *self, PyObject *args, PyObject *kwds)
{
    int rc;
    uint8_t exponent;
    const char *s;
    bool auto_decimal_place;
    bool parens_for_negatives = true;
    int64_t val;
    double dtmp;
    PyObject *pys;
    static char *kwlist[] = {
        "string", "exponent", "auto_decimal_place", "parens_for_negatives",
        NULL};

    rc = PyArg_ParseTupleAndKeywords(
        args, kwds, "Obp|p", kwlist, &pys, &exponent, &auto_decimal_place,
        &parens_for_negatives);
    if (!rc) {
        return NULL;
    }
    // `s` was previously fetches with the "s" format in
    // PyArg_ParseTupleAndKeywords(), but in rare occastions, under py37, this
    // led to strange segfaults. I had the same behavior with
    // PyUnicode_AsUTF8(). I *think* it might be related to
    // https://bugs.python.org/issue28769. Will look into it some time. For
    // now, going through PyBytes makes the problem go away.
    pys = PyUnicode_AsEncodedString(pys, "utf-8", NULL);
    if (pys == NULL) {
        return NULL;
    }
    s = PyBytes_AsString(pys);
    if (s == NULL) {
        return NULL;
    }

    if (!amount_parse_single(&val, s, exponent, auto_decimal_place)) {
        PyErr_SetString(PyExc_ValueError, "couldn't parse amount");
        return NULL;
    }
    Py_DECREF(pys);
    dtmp = (double)val / pow(10, exponent);
    return PyFloat_FromDouble(dtmp);
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
