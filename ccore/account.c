#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdio.h>
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

/* AccountList public */
void
accounts_init(AccountList *accounts, Currency *default_currency)
{
    accounts->default_currency = default_currency;
    accounts->accounts = NULL;
    accounts->count = 0;
}

void
accounts_deinit(AccountList *accounts)
{
    for (int i=0; i<accounts->count; i++) {
        account_deinit(accounts->accounts[i]);
        free(accounts->accounts[i]);
    }
    free(accounts->accounts);
}

bool
accounts_copy(AccountList *dst, const AccountList *src)
{
    accounts_init(dst, src->default_currency);
    for (int i=0; i<src->count; i++) {
        Account *a = accounts_create(dst);
        if (!account_copy(a, src->accounts[i])) {
            accounts_deinit(dst);
            return false;
        }
    }
    return true;
}

Account*
accounts_create(AccountList *accounts)
{
    Account *res = calloc(1, sizeof(Account));
    accounts->count++;
    accounts->accounts = realloc(
        accounts->accounts, sizeof(Account*) * accounts->count);
    accounts->accounts[accounts->count-1] = res;
    return res;
}

bool
accounts_remove(AccountList *accounts, Account *target)
{
    int index = -1;
    for (int i=0; i<accounts->count; i++) {
        if (accounts->accounts[i] == target) {
            index = i;
            break;
        }
    }
    if (index == -1) {
        // bad pointer
        return false;
    }
    // we have to move memory around
    memmove(
        &accounts->accounts[index],
        &accounts->accounts[index+1],
        sizeof(Account*) * (accounts->count - index - 1));
    accounts->count--;
    accounts->accounts = realloc(
        accounts->accounts, sizeof(Account*) * accounts->count);
    /* Normally, we should be freeing our account here. However, because of the
     * Undoer, we can't: it holds a reference to the deleted account and needs
     * it around in case we need it again. The best option at this time is
     * simply to never free our accounts. When the Undoer will be converted to
     * C, we can revisit our memory management model to free Accounts when it's
     * safe.
     */
    /*free(target);*/
    return true;
}

Account *
accounts_find_by_name(const AccountList *accounts, const char *name)
{
    if (name == NULL) {
        return NULL;
    }
    Account *res = NULL;
    char *dst = NULL;
    const char *trimmed;
    if (strstrip(&dst, name)) {
        trimmed = dst;
    } else {
        trimmed = name;
    }
    for (int i=0; i<accounts->count; i++) {
        Account *a = accounts->accounts[i];
        if (strcasecmp(trimmed, a->name) == 0) {
            res = a;
            break;
        }
        if (a->account_number != NULL && strcmp(trimmed, a->account_number) == 0) {
            res = a;
            break;
        }
    }
    if (dst != NULL) {
        free(dst);
    }
    return res;
}

Account*
accounts_find_by_reference(const AccountList *accounts, const char *reference)
{
    if ((reference == NULL) || (strlen(reference) == 0)) {
        return NULL;
    }
    for (int i=0; i<accounts->count; i++) {
        Account *a = accounts->accounts[i];
        if (strcmp(reference, a->reference) == 0) {
            return a;
        }
    }
    return NULL;
}
