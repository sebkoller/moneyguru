#ifndef _XOPEN_SOURCE
#define _XOPEN_SOURCE
#endif
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdbool.h>
#include <sqlite3.h>
#include <time.h>
#include "currency.h"

#define CURRENCY_REGISTRY_BLOCK 100
#define DATE_LEN 8
#define MAX_SQL_LEN 512
#define SQL_RES_LEN 512

static sqlite3 *g_db = NULL;
// Currencies are allocated in block. Whether a "slot" is registered is
// determined by whether its code starts with '\0'
static Currency *g_currencies = NULL;
static unsigned int g_currencies_count = 0;
static unsigned int g_currencies_max = 0;

// Private

static size_t
date2str(char *s, const struct tm *date)
{
    return strftime(s, DATE_LEN + 1, "%Y%m%d", date);
}

static bool
str2date(const char *s, struct tm *date)
{
    return strptime(s, "%Y%m%d", date) != NULL;
}

static bool
sqlite_getsingle_double(const char *sql, double *result)
{
    sqlite3_stmt *stmt;
    int rc;

    rc = sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        return false;
    }
    rc = sqlite3_step(stmt);
    if (rc != SQLITE_ROW) {
        sqlite3_finalize(stmt);
        return false;
    }
    if (sqlite3_column_type(stmt, 0) != SQLITE_FLOAT) {
        sqlite3_finalize(stmt);
        return false;
    }
    *result = sqlite3_column_double(stmt, 0);
    sqlite3_finalize(stmt);
    return true;
}

static bool
sqlite_getsingle_text(const char *sql, char *result)
{
    sqlite3_stmt *stmt;
    int rc;
    const unsigned char *buf;

    rc = sqlite3_prepare_v2(g_db, sql, -1, &stmt, NULL);
    if (rc != SQLITE_OK) {
        return false;
    }
    rc = sqlite3_step(stmt);
    if (rc != SQLITE_ROW) {
        sqlite3_finalize(stmt);
        return false;
    }
    buf = sqlite3_column_text(stmt, 0);
    if (buf == NULL) {
        sqlite3_finalize(stmt);
        return false;
    }
    strncpy(result, (const char *)buf, SQL_RES_LEN);
    sqlite3_finalize(stmt);
    return true;
}

static CurrencyResult
seek_value_in_CAD(struct tm *date, Currency *currency, double *result)
{
    char strdate[DATE_LEN + 1];
    char sql[MAX_SQL_LEN + 1];
    char *sqlfmt = "select rate from rates "
        "where date %s '%s' and currency = '%s' "
        "order by date %s limit 1";
    double rate;

    if (strncmp(currency->code, "CAD", CURRENCY_CODE_MAXLEN) == 0) {
        *result = 1;
        return CURRENCY_OK;
    }
    if (mktime(date) < currency->start_date) {
        *result = currency->start_rate;
        return CURRENCY_OK;
    }
    if (currency->stop_date > 0 && mktime(date) > currency->stop_date) {
        *result = currency->latest_rate;
        return CURRENCY_OK;
    }
    date2str(strdate, date);
    snprintf(
        sql, MAX_SQL_LEN, sqlfmt,
        "<=", strdate, currency->code, "desc");
    if (!sqlite_getsingle_double(sql, &rate)) {
        snprintf(
            sql, MAX_SQL_LEN, sqlfmt,
            ">=", strdate, currency->code, "");
        if (!sqlite_getsingle_double(sql, &rate)) {
            return CURRENCY_NORESULT;
        }
    }
    *result = rate;
    return CURRENCY_OK;
}

// Public
CurrencyResult
currency_global_init(char *dbpath)
{
    int res;

    if (g_currencies == NULL) {
        res = currency_global_reset_currencies();
        if (res != CURRENCY_OK) {
            return res;
        }
    }
    if (g_db != NULL) {
        // We already have an opened DB. close it first.
        sqlite3_close(g_db);
        g_db = NULL;
    }
    res = sqlite3_open(dbpath, &g_db);
    if (res) {
        sqlite3_close(g_db);
        return CURRENCY_ERROR;
    }
    res = sqlite3_exec(g_db, "select * from rates where 1=2", NULL, NULL, NULL);
    if (res) {
        // We have to create tables
        sqlite3_exec(
            g_db,
            "create table rates(date TEXT, currency TEXT, rate REAL NOT NULL)",
            NULL, NULL, NULL);
        sqlite3_exec(
            g_db,
            "create unique index idx_rate on rates (date, currency)",
            NULL, NULL, NULL);
    }
    return CURRENCY_OK;
}

CurrencyResult
currency_global_reset_currencies()
{
    if (g_currencies != NULL) {
        // Don't allocate a new list, we're probably in a test context and we
        // want to keep our 3 main currency instances. Flush the rest of the
        // list
        for (unsigned int i=3; i<g_currencies_count; i++) {
            g_currencies[i].code[0] = '\0';
        }
        g_currencies_count = 3;
        return CURRENCY_OK;
    }
    g_currencies = calloc(CURRENCY_REGISTRY_BLOCK, sizeof(Currency));
    if (g_currencies == NULL) {
        return CURRENCY_ERROR;
    }
    g_currencies_max = CURRENCY_REGISTRY_BLOCK;
    // Register our 3 base currencies
    currency_register(
        "USD",
        2,
        883717200, // 1998-01-02
        1.425,
        0,
        1.0128);
    currency_register(
        "EUR",
        2,
        915426000, // 1999-01-04
        1.8123,
        0,
        1.3298);
    currency_register(
        "CAD",
        2,
        0,
        1,
        0,
        1);
    return CURRENCY_OK;
}

void
currency_global_deinit()
{
    if (g_db != NULL) {
        sqlite3_close(g_db);
        g_db = NULL;
    }
    if (g_currencies != NULL) {
        free(g_currencies);
    }
}

Currency*
currency_register(
    char *code,
    unsigned int exponent,
    time_t start_date,
    double start_rate,
    time_t stop_date,
    double latest_rate)
{
    Currency *cur;

    cur = currency_get(code);
    if (cur != NULL) {
        return cur;
    }

    if (g_currencies_count == g_currencies_max) {
        // We need to allocate more currency space.
        cur = realloc(
            g_currencies,
            (g_currencies_max + CURRENCY_REGISTRY_BLOCK) * sizeof(Currency));
        if (cur == NULL) {
            return NULL;
        }
        g_currencies = cur;
        g_currencies_max += CURRENCY_REGISTRY_BLOCK;
        for (unsigned int i=g_currencies_count; i<g_currencies_max; i++) {
            g_currencies[i].code[0] = '\0';
        }
    }
    cur = &g_currencies[g_currencies_count];
    strncpy(cur->code, code, CURRENCY_CODE_MAXLEN);
    cur->exponent = exponent;
    cur->start_date = start_date;
    cur->start_rate = start_rate;
    cur->stop_date = stop_date;
    cur->latest_rate = latest_rate;
    g_currencies_count++;
    return cur;
}

Currency*
currency_get(const char *code)
{
    if (g_currencies == NULL) {
        currency_global_init(":memory:");
    }

    if (!strlen(code)) {
        return NULL;
    }

    for (unsigned int i=0; i<g_currencies_count; i++) {
        if (strncmp(code, g_currencies[i].code, CURRENCY_CODE_MAXLEN) == 0) {
            return &g_currencies[i];
        }
    }
    return NULL;
}

CurrencyResult
currency_getrate(struct tm *date, Currency *c1, Currency *c2, double *result)
{
    double value1 = 1;
    double value2 = 1;
    CurrencyResult res;

    if (strncmp(c1->code, c2->code, CURRENCY_CODE_MAXLEN) == 0) {
        *result = 1;
        return CURRENCY_OK;
    }
    res = seek_value_in_CAD(date, c1, &value1);
    if (res == CURRENCY_NORESULT) {
        value1 = c1->latest_rate;
    }
    res = seek_value_in_CAD(date, c2, &value2);
    if (res == CURRENCY_NORESULT) {
        value2 = c2->latest_rate;
    }
    if (value2 != 0) {
        *result = value1 / value2;
    } else {
        *result = 1;
    }
    return CURRENCY_OK;
}

void
currency_set_CAD_value(struct tm *date, Currency *currency, double value)
{
    char strdate[DATE_LEN + 1];
    char sql[MAX_SQL_LEN + 1];

    date2str(strdate, date);
    snprintf(
        sql, MAX_SQL_LEN,
        "replace into rates(date, currency, rate) values('%s', '%s', %0.6f)",
        strdate, currency->code, value);
    sqlite3_exec(g_db, sql, NULL, NULL, NULL);
    sqlite3_exec(g_db, "commit", NULL, NULL, NULL);
}

bool
currency_daterange(Currency *currency, struct tm *start, struct tm *stop)
{
    char sql[MAX_SQL_LEN + 1];
    char buf[SQL_RES_LEN + 1] = {0};

    snprintf(
        sql, MAX_SQL_LEN,
        "select min(date) from rates where currency = '%s'",
        currency->code);
    if (!sqlite_getsingle_text(sql, buf)) {
        return false;
    }
    if (!str2date(buf, start)) {
        return false;
    }
    snprintf(
        sql, MAX_SQL_LEN,
        "select max(date) from rates where currency = '%s'",
        currency->code);
    if (!sqlite_getsingle_text(sql, buf)) {
        return false;
    }
    if (!str2date(buf, stop)) {
        return false;
    }
    return true;
}
