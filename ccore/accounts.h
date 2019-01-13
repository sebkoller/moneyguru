#pragma once

#include <glib.h>
#include "account.h"
#include "entry.h"

typedef struct {
    Currency *default_currency;
    int count;
    Account **accounts;
    GHashTable *a2entries;
    // Where we put our deleted accounts so that we can undelete them
    GPtrArray *trashcan;
} AccountList;

void
accounts_init(AccountList *accounts, Currency *default_currency);

void
accounts_deinit(AccountList *accounts);

// dst must be uninitalized
bool
accounts_copy(AccountList *dst, const AccountList *src);

Account*
accounts_create(AccountList *accounts);

EntryList*
accounts_entries_for_account(AccountList *accounts, Account *account);

bool
accounts_remove(AccountList *accounts, Account *todelete);

bool
accounts_rename(AccountList *accounts, Account *target, const char *newname);

bool
accounts_undelete(AccountList *accounts, Account *torestore);

/* Returns the first account that matches `name`.
 *
 * If `name` matches the account's `account_number`, we consider this a match.
 *
 * NOTE: can return a deleted account
 */
Account*
accounts_find_by_name(const AccountList *accounts, const char *name);

// Doesn't search in deleted accounts
Account*
accounts_find_by_reference(const AccountList *accounts, const char *reference);

