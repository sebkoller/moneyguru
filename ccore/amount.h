#include <stdint.h>
#include <stdbool.h>

#include "currency.h"

typedef struct {
    int64_t val;
    Currency *currency;
} Amount;

Amount*
amount_init(int64_t val, Currency *currency);

Amount*
amount_zero();

bool
amount_check(Amount *first, Amount *second);

void
amount_free(Amount *amount);
