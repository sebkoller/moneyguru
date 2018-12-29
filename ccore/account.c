#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "account.h"
#include "amount.h"
#include "util.h"

/* Account public */
void
account_init(
    Account *account,
    const char *name,
    Currency *currency,
    AccountType type)
{
    account->name = NULL;
    account_name_set(account, name);
    account->currency = currency;
    account->type = type;
    account->inactive = false;
    account->account_number = "";
    account->notes = "";
    account->autocreated = false;
}

void
account_deinit(Account *account)
{
    strfree(&account->name);
    strfree(&account->reference);
    strfree(&account->groupname);
    strfree(&account->account_number);
    strfree(&account->notes);
}

bool
account_copy(Account *dst, const Account *src)
{
    if (dst == src) {
        // not supposed to be tried
        return false;
    }
    dst->type = src->type;
    dst->currency = src->currency;
    if (!strclone(&dst->name, src->name)) {
        return false;
    }
    dst->inactive = src->inactive;
    if (!strclone(&dst->reference, src->reference)) {
        return false;
    }
    if (!strclone(&dst->account_number, src->account_number)) {
        return false;
    }
    if (!strclone(&dst->notes, src->notes)) {
        return false;
    }
    if (!strclone(&dst->groupname, src->groupname)) {
        return false;
    }
    dst->autocreated = src->autocreated;
    return true;
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

void
account_name_set(Account *account, const char *name)
{
    char *dst = NULL;
    if (strstrip(&dst, name)) {
        strset(&account->name, dst);
        free(dst);
    } else {
        strset(&account->name, name);
    }
}

void
account_normalize_amount(Account *account, Amount *dst)
{
    if (account_is_credit(account)) {
        dst->val *= -1;
    }
}
