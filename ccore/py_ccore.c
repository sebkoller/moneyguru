#include <Python.h>
#include "currency.h"

PyType_Spec Amount_Type_Spec;
PyObject *Amount_Type;
PyObject* py_amount_format(PyObject *self, PyObject *args, PyObject *kwds);
PyObject* py_amount_parse_single(PyObject *self, PyObject *args, PyObject *kwds);

PyObject* py_currency_global_init(PyObject *self, PyObject *args);
PyObject* py_currency_register(PyObject *self, PyObject *args);
PyObject* py_currency_getrate(PyObject *self, PyObject *args);
PyObject* py_currency_set_CAD_value(PyObject *self, PyObject *args);
PyObject* py_currency_daterange(PyObject *self, PyObject *args);
PyObject* py_currency_exponent(PyObject *self, PyObject *args);

static PyMethodDef module_methods[] = {
    {"amount_format", (PyCFunction)py_amount_format, METH_VARARGS | METH_KEYWORDS},
    {"amount_parse_single", (PyCFunction)py_amount_parse_single, METH_VARARGS | METH_KEYWORDS},
    {"currency_global_init", py_currency_global_init, METH_VARARGS},
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
    return m;
}

