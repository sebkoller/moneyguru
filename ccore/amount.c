#include <stdlib.h>

#include "amount.h"

static Amount *g_zero = NULL;


Amount*
amount_init(int64_t val, Currency *currency)
{
    Amount *res;

    res = malloc(sizeof(Amount));
    if (res == NULL) {
        return NULL;
    }
    res->val = val;
    res->currency = currency;
    return res;
}

Amount*
amount_zero()
{
    if (g_zero == NULL) {
        g_zero = amount_init(0, NULL);
    }
    return g_zero;
}

bool
amount_check(Amount *first, Amount *second)
{
    if (!(first && second)) {
        // A NULL amount? not cool.
        return false;
    }
    if (first->val && second->val) {
        return first->currency == second->currency;
    } else {
        // One of them is zero. compatible.
        return true;
    }
}

void
amount_free(Amount *amount)
{
    if (amount != NULL) {
        free(amount);
    }
}
