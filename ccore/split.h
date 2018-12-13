#pragma once

#include <time.h>
#include "amount.h"

typedef struct {
    Amount amount;
    int account_id;
    // Date at which the user reconciled this split with an external source.
    time_t reconciliation_date;
} Split;
