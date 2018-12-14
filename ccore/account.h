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
    // Name of the account. Must be unique in the whole document.
    char *name;
    // External reference number (like, for example, a reference given by a
    // bank). Used to uniquely match an account in moneyGuru to one being
    // imported from another source.
    char *reference;
    // group name in which this account belongs. Can be `None` (no group).
    char *groupname;
    // Unique account identifier. Can be used instead of the account name in
    // the UI (faster than typing the name if you know your numbers).
    char *account_number;
    // Freeform notes about the account.
    char *notes;
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
