#include <Python.h>
#include "currency.h"

PyType_Spec Amount_Type_Spec;
PyObject *Amount_Type;

PyType_Spec Currency_Type_Spec;
PyObject *Currency_Type;
PyObject* py_currency_global_init(PyObject *self, PyObject *args);
PyObject* py_currency_register(PyObject *self, PyObject *args);
PyObject* py_currency_getrate(PyObject *self, PyObject *args);
PyObject* py_currency_set_CAD_value(PyObject *self, PyObject *args);
PyObject* py_currency_daterange(PyObject *self, PyObject *args);

static PyMethodDef module_methods[] = {
    {"currency_global_init",  py_currency_global_init, METH_VARARGS},
    {"currency_register",  py_currency_register, METH_VARARGS},
    {"currency_getrate", py_currency_getrate, METH_VARARGS},
    {"currency_set_CAD_value", py_currency_set_CAD_value, METH_VARARGS},
    {"currency_daterange", py_currency_daterange, METH_VARARGS},
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

    Currency_Type = PyType_FromSpec(&Currency_Type_Spec);
    Amount_Type = PyType_FromSpec(&Amount_Type_Spec);

    m = PyModule_Create(&CCoreDef);
    if (m == NULL) {
        return NULL;
    }

    PyModule_AddObject(m, "Currency", Currency_Type);
    PyModule_AddObject(m, "Amount", Amount_Type);
    return m;
}

