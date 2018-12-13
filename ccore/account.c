#include "account.h"
#include "amount.h"

static int _g_account_counter = 0;

int
account_newid()
{
    _g_account_counter++;
    return _g_account_counter;
}

void
account_normalize_amount(Account *account, Amount *dst)
{
    if (account_is_credit(account)) {
        dst->val *= -1;
    }
}

bool
account_is_balance_sheet(Account *account)
{
    return account->type == ACCOUNT_ASSET || account->type == ACCOUNT_LIABILITY;
}

bool
account_is_credit(Account *account)
{
    return account->type == ACCOUNT_LIABILITY || account->type == ACCOUNT_INCOME;
}

bool
account_is_debit(Account *account)
{
    return account->type == ACCOUNT_ASSET || account->type == ACCOUNT_EXPENSE;
}

bool
account_is_income_statement(Account *account)
{
    return account->type == ACCOUNT_INCOME || account->type == ACCOUNT_EXPENSE;
}

