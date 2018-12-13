#pragma once

#include <stdbool.h>
#include "amount.h"
#include "currency.h"

typedef enum {
    ACCOUNT_ASSET = 1,
    ACCOUNT_LIABILITY = 2,
    ACCOUNT_INCOME = 3,
    ACCOUNT_EXPENSE = 4
} AccountType;

typedef struct {
    int id;
    AccountType type;
    // Default currency of the account. Mostly determines how amounts are
    // displayed when viewing its entries listing.
    Currency *currency;
    // Inactive accounts don't show up in auto-complete.
    bool inactive;
} Account;

int
account_newid();

void
account_normalize_amount(Account *account, Amount *dst);

bool
account_is_balance_sheet(Account *account);

bool
account_is_credit(Account *account);

bool
account_is_debit(Account *account);

bool
account_is_income_statement(Account *account);
