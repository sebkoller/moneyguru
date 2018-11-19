#define Py_LIMITED_API
#include <Python.h>
#include <math.h>
#include "amount.h"

typedef struct {
    PyObject_HEAD
    Amount amount;
    PyObject *currency; /* a Currency instance */
    PyObject *rval; /* Real value, as a python float instance */
} PyAmount;

static PyObject *Amount_Type;

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
set_currency(PyAmount *amount, PyObject *currency)
{
    PyObject *tmp;

    tmp = amount->currency;
    amount->currency = currency;
    Py_XDECREF(tmp);

    tmp = PyObject_GetAttrString(currency, "_inner");
    if (tmp == NULL) {
        return false;
    }
    if (!PyCapsule_CheckExact(tmp)) {
        Py_DECREF(tmp);
        return false;
    }
    amount->amount.currency = (Currency *)PyCapsule_GetPointer(tmp, NULL);
    Py_DECREF(tmp);
    if (amount->currency == NULL) {
        return false;
    }
    return true;
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

static int
check_amounts(PyObject *a, PyObject *b, int seterr)
{
    /* Verify that a and b are amounts and compatible together and returns true or false.
       if seterr is true, an appropriate error is set.
    */
    if (!check_amount(a) || !check_amount(b)) {
        if (seterr) {
            PyErr_SetString(PyExc_TypeError, "Amounts can only be compared with other amounts or zero.");
        }
        return 0;
    }

    if (!amounts_are_compatible(a, b)) {
        if (seterr) {
            PyErr_SetString(PyExc_ValueError, "Amounts of different currencies can't be compared.");
        }
        return 0;
    }

    return 1;
}

static PyObject *
create_amount(int64_t ival, PyObject *currency)
{
    /* Create a new amount in a way that is faster than the normal init */
    PyAmount *r;
    double dtmp;
    int exponent;

    r = (PyAmount *)PyType_GenericAlloc((PyTypeObject *)Amount_Type, 0);
    r->amount.val = ival;
    if (!set_currency(r, currency)) {
        return NULL;
    }
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
    Py_XDECREF(self->currency);
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
    self->currency = Py_None;
    Py_INCREF(self->currency);
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
    PyObject *amount, *currency, *tmp;
    double dtmp;

    static char *kwlist[] = {"amount", "currency", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "OO", kwlist, &amount, &currency)) {
        return -1;
    }

    if (!set_currency(self, currency)) {
        return -1;
    }
    dtmp = PyFloat_AsDouble(amount);
    if (dtmp == -1 && PyErr_Occurred()) {
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
    Py_VISIT(self->currency);
    return 0;
}

static int
PyAmount_clear(PyAmount *self)
{
    Py_CLEAR(self->rval);
    Py_CLEAR(self->currency);
    return 0;
}

static PyObject *
PyAmount_copy(PyObject *self)
{
    return create_amount(
        ((PyAmount *)self)->amount.val,
        ((PyAmount *)self)->currency);
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
        "(iOO)", self->amount.currency->exponent, self->rval, self->currency);
    fmt = PyUnicode_FromString("Amount(%.*f, %r)");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static Py_hash_t
PyAmount_hash(PyAmount *self)
{
    PyObject *hash_tuple, *int_value;
    Py_hash_t r;

    int_value = PyLong_FromLongLong(self->amount.val);
    hash_tuple = PyTuple_Pack(2, int_value, self->currency);
    Py_DECREF(int_value);
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
    return create_amount(-self->amount.val, self->currency);
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

    if (!check_amounts(a, b, 1)) {
        return NULL;
    }
    aval = get_amount(a)->val;
    bval = get_amount(b)->val;
    if (aval && bval) {
        currency = ((PyAmount *)a)->currency;
        return create_amount(aval + bval, currency);
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
        currency = ((PyAmount *)a)->currency;
        return create_amount(aval - bval, currency);
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
    return create_amount(ival, ((PyAmount *)a)->currency);
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
    return create_amount(ival, ((PyAmount *)a)->currency);
}

static PyObject *
PyAmount_getcurrency(PyAmount *self)
{
    Py_INCREF(self->currency);
    return self->currency;
}

static PyObject *
PyAmount_getvalue(PyAmount *self)
{
    Py_INCREF(self->rval);
    return self->rval;
}

/* We need both __copy__ and __deepcopy__ methods for amounts to behave correctly in undo_test. */

static PyMethodDef PyAmount_methods[] = {
    {"__copy__", (PyCFunction)PyAmount_copy, METH_NOARGS, ""},
    {"__deepcopy__", (PyCFunction)PyAmount_deepcopy, METH_VARARGS, ""},
    {0, 0, 0, 0},
};

static PyGetSetDef PyAmount_getseters[] = {
    {"currency", (getter)PyAmount_getcurrency, NULL, "currency", NULL},
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
