#define Py_LIMITED_API
#include <Python.h>
#include "currency.h"

PyType_Spec Amount_Type_Spec;
static PyObject *Amount_Type;

PyType_Spec Currency_Type_Spec;
static PyObject *Currency_Type;
PyObject* py_currency_global_init(PyObject *self, PyObject *args);
PyObject* py_currency_register(PyObject *self, PyObject *args);

static PyMethodDef module_methods[] = {
    {"currency_global_init",  py_currency_global_init, METH_VARARGS},
    {"currency_register",  py_currency_register, METH_VARARGS},
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

    /*currency_global_init(":memory:");*/
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

