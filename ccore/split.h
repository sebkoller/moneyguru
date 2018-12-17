#pragma once

#include <time.h>
#include "amount.h"
#include "account.h"

typedef struct {
    Amount amount;
    Account *account;
    // Date at which the user reconciled this split with an external source.
    time_t reconciliation_date;
    // Freeform memo about that split.
    char *memo;
    // Unique reference from an external source.
    char *reference;
} Split;

void
split_init(Split *split, Account *account, const Amount *amount);

void
split_account_set(Split *split, Account *account);

void
split_amount_set(Split *split, const Amount *amount);

bool
split_copy(Split *dst, const Split *src);

void
split_deinit(Split *split);

