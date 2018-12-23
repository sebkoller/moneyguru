#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "account.h"
#include "amount.h"
#include "util.h"

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

bool
account_copy(Account *dst, const Account *src)
{
    if (dst == src) {
        // not supposed to be tried
        return false;
    }
    if (src->id < 1) {
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
    dst->deleted = src->deleted;
    return true;
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

// TODO: test realloc conditions
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

Account *
accounts_find_by_name(const AccountList *accounts, const char *name)
{
    if (name == NULL) {
        return NULL;
    }
    for (int i=0; i<accounts->count; i++) {
        // id == 0 means deleted or not initialized
        if (accounts->accounts[i].id > 0) {
            if (strcmp(name, accounts->accounts[i].name) == 0) {
                return &accounts->accounts[i];
            }
        }
    }
    return NULL;
}

Account*
accounts_find_by_reference(const AccountList *accounts, const char *reference)
{
    if ((reference == NULL) || (strlen(reference) == 0)) {
        return NULL;
    }
    for (int i=0; i<accounts->count; i++) {
        Account *a = &accounts->accounts[i];
        // id == 0 means deleted or not initialized
        if (a->id > 0 && !a->deleted) {
            if (strcmp(reference, a->reference) == 0) {
                return a;
            }
        }
    }
    return NULL;
}

bool
accounts_copy(AccountList *dst, const AccountList *src)
{
    accounts_init(dst, src->count, src->default_currency);
    dst->id_counter = src->id_counter;
    for (int i=0; i<dst->count; i++) {
        if (src->accounts[i].id < 1) continue;
        if (!account_copy(&dst->accounts[i], &src->accounts[i])) {
            return false;
        }
    }
    return true;
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
