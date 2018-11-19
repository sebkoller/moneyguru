#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <sqlite3.h>
#include "currency.h"

#define CURRENCY_REGISTRY_INITIAL_SIZE 200
#define DATE_LEN 8
#define MAX_SQL_LEN 512

static sqlite3 *g_db = NULL;
static Currency **g_currencies = NULL;
static float g_fetched_rate;

// Private

static size_t
date2str(char *s, const struct tm *date)
{
    return strftime(s, DATE_LEN + 1, "%Y%m%d", date);
}

static int
seek_value_in_CAD_callback(void *notused, int argc, char **argv, char **colname)
{
    g_fetched_rate = atof(argv[0]);
    return 0;
}

static CurrencyResult
seek_value_in_CAD(char *strdate, Currency *currency, float *result)
{
    char sql[MAX_SQL_LEN + 1];
    char *sqlfmt = "select rate from rates "
        "where date %s '%s' and currency = '%s' "
        "order by date %s limit 1";
    int res;

    if (strncmp(currency->code, "CAD", CURRENCY_CODE_MAXLEN) == 0) {
        *result = 1;
        return CURRENCY_OK;
    }
    snprintf(
        sql, MAX_SQL_LEN, sqlfmt,
        "<=", strdate, currency->code, "desc");
    g_fetched_rate = -1;
    sqlite3_exec(g_db, sql, seek_value_in_CAD_callback, NULL, NULL);
    if (g_fetched_rate < 0) {
        snprintf(
            sql, MAX_SQL_LEN, sqlfmt,
            ">=", strdate, currency->code, "");
        sqlite3_exec(g_db, sql, seek_value_in_CAD_callback, NULL, NULL);
        if (g_fetched_rate < 0) {
            return CURRENCY_NORESULT;
        }
    } else {
        *result = g_fetched_rate;
        return CURRENCY_OK;
    }
}

// Public
CurrencyResult
currency_global_init(char *dbpath)
{
    int res;

    g_currencies = calloc(CURRENCY_REGISTRY_INITIAL_SIZE, sizeof(Currency*));
    if (g_currencies == NULL) {
        return CURRENCY_ERROR;
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
currency_register(char *code, unsigned int exponent)
{
    Currency *cur;

    cur = currency_get(code);
    if (cur != NULL) {
        return cur;
    }

    cur = malloc(sizeof(Currency));
    if (cur == NULL) {
        return NULL;
    }
    strncpy(cur->code, code, CURRENCY_CODE_MAXLEN);
    cur->exponent = exponent;

    for (int i=0; i<CURRENCY_REGISTRY_INITIAL_SIZE; i++) {
        if (g_currencies[i] == NULL) {
            g_currencies[i] = cur;
            return cur;
        }
    }
    // something's wrong
    free(cur);
    return NULL;
}

Currency*
currency_get(char *code)
{
    Currency **cur;

    if (g_currencies == NULL) {
        currency_global_init(":memory:");
    }

    cur = g_currencies;
    while (*cur != NULL) {
        if (strncmp(code, (*cur)->code, CURRENCY_CODE_MAXLEN) == 0) {
            return *cur;
        }
        cur++;
    }
    return NULL;
}

CurrencyResult
currency_getrate(struct tm *date, Currency *c1, Currency *c2, float *result)
{
    float value1 = 1;
    float value2 = 1;
    char strdate[DATE_LEN + 1];
    CurrencyResult res;

    if (strncmp(c1->code, c2->code, CURRENCY_CODE_MAXLEN) == 0) {
        *result = 1;
        return CURRENCY_OK;
    }

    date2str(strdate, date);
    if (strncmp(c1->code, "CAD", CURRENCY_CODE_MAXLEN) != 0) {
        res = seek_value_in_CAD(strdate, c1, &value1);
        if (res != CURRENCY_OK) {
            return res;
        }
    }
    if (strncmp(c2->code, "CAD", CURRENCY_CODE_MAXLEN) != 0) {
        res = seek_value_in_CAD(strdate, c2, &value2);
        if (res != CURRENCY_OK) {
            return res;
        }
    }
    *result = value1 / value2;
    return CURRENCY_OK;
}

void
currency_set_CAD_value(struct tm *date, Currency *currency, float value)
{
    char strdate[DATE_LEN + 1];
    char sql[MAX_SQL_LEN + 1];

    date2str(strdate, date);
    snprintf(
        sql, MAX_SQL_LEN,
        "replace into rates(date, currency, rate) values('%s', '%s', %0.4f)",
        strdate, currency->code, value);
    sqlite3_exec(g_db, sql, NULL, NULL, NULL);
    sqlite3_exec(g_db, "commit", NULL, NULL, NULL);
}
