#include <stdlib.h>
#include <string.h>
#include "account.h"
#include "amount.h"

/* Common code */

/* Frees a string created through strset() in py_ccore.c
 *
 * Returns false on error
 */
static bool
strfree(char **dst)
{
    if (dst == NULL) {
        // not supposed to happen
        return false;
    }
    if (*dst == NULL || *dst[0] == '\0') {
        // nothing to free
        return true;
    }
    free(*dst);
    *dst = NULL;
    return true;
}

/* Account public */
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

void
account_deinit(Account *account)
{
    strfree(&account->name);
    strfree(&account->reference);
    strfree(&account->groupname);
    strfree(&account->account_number);
    strfree(&account->notes);
}

/* AccountList private */
static int
_accounts_find_free_slot(AccountList *accounts)
{
    for (int i=0; i<accounts->count; i++) {
        if (accounts->accounts[i].id <= 0) {
            return i;
        }
    }
    return -1;
}

/* AccountList public */
void
accounts_init(AccountList *accounts, int initial_count, Currency *default_currency)
{
    accounts->default_currency = default_currency;
    accounts->count = initial_count;
    int bytecount = sizeof(Account) * initial_count;
    accounts->accounts = malloc(bytecount);
    memset(accounts->accounts, 0, bytecount);
    accounts->id_counter = 1;
}

Account*
accounts_create(AccountList *accounts)
{
    int index = _accounts_find_free_slot(accounts);
    if (index < 0) {
        // Not enough free slots, reallocating
        index = accounts->count;
        accounts->count *= 2;
        int bytecount = sizeof(Account) * accounts->count;
        // initialize the second half
        memset(&accounts->accounts[index], 0, bytecount/2);
    }
    Account *res = &accounts->accounts[index];
    memset(res, 0, sizeof(Account));
    res->id = accounts->id_counter++;
    return res;
}

void
accounts_deinit(AccountList *accounts)
{
    for (int i=0; i<accounts->count; i++) {
        if (accounts->accounts[i].id > 0) {
            account_deinit(&accounts->accounts[i]);
        }
    }
    free(accounts->accounts);
}
