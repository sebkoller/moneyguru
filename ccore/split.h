#pragma once

#include <time.h>
#include "amount.h"
#include "account.h"

typedef struct {
    Amount amount;
    Account *account;
    // Date at which the user reconciled this split with an external source.
    time_t reconciliation_date;
} Split;
