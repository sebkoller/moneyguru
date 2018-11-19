#define Py_LIMITED_API
#include <Python.h>
#include <math.h>
#include "currency.h"

typedef struct {
    PyObject_HEAD
    Currency *currency;
} PyCurrency;

static PyObject *Currency_Type;

#define Currency_Check(v) (Py_TYPE(v) == (PyTypeObject *)Currency_Type)

/* Functions */
PyObject* py_currency_global_init(PyObject *self, PyObject *args)
{
    char *dbpath;

    if (!PyArg_ParseTuple(args, "s", &dbpath)) {
        return NULL;
    }

    currency_global_init(dbpath);
    Py_INCREF(Py_None);
    return Py_None;
}

PyObject* py_currency_register(PyObject *self, PyObject *args)
{
    char *code;
    int exponent;

    if (!PyArg_ParseTuple(args, "si", &code, &exponent)) {
        return NULL;
    }

    currency_register(code, exponent);
    Py_INCREF(Py_None);
    return Py_None;
}

/* Methods */

static PyObject *
PyCurrency_getcode(PyCurrency *self)
{
    return PyUnicode_FromString(self->currency->code);
}

static PyObject *
PyCurrency_getexponent(PyCurrency *self)
{
    return PyLong_FromLong(self->currency->exponent);
}

static PyObject *
PyCurrency_get_inner(PyCurrency *self)
{
    return PyCapsule_New(&self->currency, NULL, NULL);
}

static int
PyCurrency_init(PyCurrency *self, PyObject *args, PyObject *kwds)
{
    char *code;
    static char *kwlist[] = {"code", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, kwds, "s", kwlist, &code)) {
        return -1;
    }
    self->currency = currency_get(code);
    if (self->currency == NULL) {
        PyErr_SetString(PyExc_ValueError, "Currency not registered foo");
        return -1;
    }
    return 0;
}

static PyObject *
PyCurrency_repr(PyCurrency *self)
{
    PyObject *r, *fmt, *args, *code;

    code = PyCurrency_getcode(self);
    args = Py_BuildValue("(O)", code);
    Py_DECREF(code);
    fmt = PyUnicode_FromString("Currency(%r)");
    r = PyUnicode_Format(fmt, args);
    Py_DECREF(fmt);
    Py_DECREF(args);
    return r;
}

static Py_hash_t
PyCurrency_hash(PyCurrency *self)
{
    PyObject *code;
    Py_hash_t r;

    code = PyCurrency_getcode(self);
    r = PyObject_Hash(code);
    Py_DECREF(code);
    return r;
}

/* Defs */

static PyGetSetDef PyCurrency_getseters[] = {
    {"code", (getter)PyCurrency_getcode, NULL, "code", NULL},
    {"exponent", (getter)PyCurrency_getexponent, NULL, "exponent", NULL},
    {"_inner", (getter)PyCurrency_get_inner, NULL, "_inner", NULL},
    {0, 0, 0, 0, 0},
};

static PyType_Slot Currency_Slots[] = {
    {Py_tp_init, PyCurrency_init},
    {Py_tp_repr, PyCurrency_repr},
    {Py_tp_hash, PyCurrency_hash},
    {Py_tp_getset, PyCurrency_getseters},
    {0, 0},
};

PyType_Spec Currency_Type_Spec = {
    "_ccore.Currency",
    sizeof(PyCurrency),
    0,
    Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE,
    Currency_Slots,
};
