#include <time.h>

#define CURRENCY_CODE_MAXLEN 4

typedef struct {
    char code[CURRENCY_CODE_MAXLEN+1];
    unsigned int exponent;
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
currency_register(char *code, unsigned int exponent);

Currency*
currency_get(char *code);

CurrencyResult
currency_getrate(struct tm *date, Currency *c1, Currency *c2, float *result);

void
currency_set_CAD_value(struct tm *date, Currency *currency, float value);
