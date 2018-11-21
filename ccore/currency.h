#include <stdbool.h>
#include <time.h>

#define CURRENCY_CODE_MAXLEN 4
#define CURRENCY_MAX_EXPONENT 10

typedef struct {
    char code[CURRENCY_CODE_MAXLEN+1];
    unsigned int exponent;
    time_t start_date;
    double start_rate;
    time_t stop_date;
    double latest_rate;
} Currency;

typedef enum {
    CURRENCY_OK = 0,
    CURRENCY_NORESULT = 1,
    CURRENCY_ERROR = 2,
} CurrencyResult;

CurrencyResult
currency_global_init(char *dbpath);

void
currency_global_deinit();

Currency*
currency_register(
    char *code,
    unsigned int exponent,
    time_t start_date,
    double start_rate,
    time_t stop_date,
    double latest_rate);

Currency*
currency_get(const char *code);

CurrencyResult
currency_getrate(struct tm *date, Currency *c1, Currency *c2, double *result);

void
currency_set_CAD_value(struct tm *date, Currency *currency, double value);

bool
currency_daterange(Currency *currency, struct tm *start, struct tm *stop);
