#include <Python.h>
#include <datetime.h>
#include <math.h>
#include <stdbool.h>
#include "currency.h"

/* Utils */
static bool
pydate2tm(PyObject *pydate, struct tm *dest)
{
    if (!PyDate_Check(pydate)) {
        PyErr_SetString(PyExc_ValueError, "pydate2tm needs a date value");
        return false;
    }
    dest->tm_year = PyDateTime_GET_YEAR(pydate) - 1900;
    dest->tm_mon = PyDateTime_GET_MONTH(pydate);
    dest->tm_mday = PyDateTime_GET_DAY(pydate);
    return true;
}

static PyObject*
tm2pydate(struct tm *date)
{
    return PyDate_FromDate(date->tm_year + 1900, date->tm_mon, date->tm_mday);
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

/* Functions */
PyObject*
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

PyObject*
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

PyObject*
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

    c1 = getcur(code1);
    if (c1 == NULL) {
        return NULL;
    }
    c2 = getcur(code2);
    if (c2 == NULL) {
        return NULL;
    }
    if (currency_getrate(&date, c1, c2, &rate) != CURRENCY_OK) {
        Py_INCREF(Py_None);
        return Py_None;
    }
    return PyFloat_FromDouble(rate);
}

PyObject*
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

PyObject*
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

    c = getcur(code);
    if (c == NULL) {
        return NULL;
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

PyObject *
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
