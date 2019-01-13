#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "undo.h"
#include "util.h"

/* Private */
static bool
_remove_accounts(Account **accounts, AccountList *alist)
{
    while (*accounts != NULL) {
        if (!accounts_remove(alist, *accounts)) {
            return false;
        }
        accounts++;
    }
    return true;
}

static bool
_readd_accounts(Account **accounts, AccountList *alist)
{
    while (*accounts != NULL) {
        if (!accounts_undelete(alist, *accounts)) {
            return false;
        }
        accounts++;
    }
    return true;
}

static bool
_swap_accounts(ChangedAccount *accounts, int count)
{
    for (int i=0; i<count; i++) {
        ChangedAccount *c = &accounts[i];
        Account tmp;
        if (c->account == NULL) {
            return false;
        }
        // We don't use account_copy() because we don't have to mess with
        // string ownership: these ownerships follow cleanly with a simple
        // memcpy().
        memcpy(&tmp, c->account, sizeof(Account));
        memcpy(c->account, &c->copy, sizeof(Account));
        memcpy(&c->copy, &tmp, sizeof(Account));
    }
    return true;
}

/* Public */
void
undostep_init(
    UndoStep *step,
    Account **added_accounts,
    Account **deleted_accounts,
    Account **changed_accounts)
{
    int count = listlen((void *)added_accounts);
    step->added_accounts = malloc(sizeof(Account*) * (count + 1));
    memcpy(step->added_accounts, added_accounts, sizeof(Account*) * (count + 1));
    count = listlen((void *)deleted_accounts);
    step->deleted_accounts = malloc(sizeof(Account*) * (count + 1));
    memcpy(step->deleted_accounts, deleted_accounts, sizeof(Account*) * (count + 1));
    step->changed_count = listlen((void *)changed_accounts);
    step->changed_accounts = calloc(sizeof(ChangedAccount), step->changed_count);
    for (int i=0; i<step->changed_count; i++) {
        ChangedAccount *c = &step->changed_accounts[i];
        c->account = changed_accounts[i];
        account_copy(&c->copy, c->account);
    }
}

void
undostep_deinit(UndoStep *step)
{
    free(step->added_accounts);
    step->added_accounts = NULL;
    free(step->deleted_accounts);
    step->deleted_accounts = NULL;
    for (int i=0; i<step->changed_count; i++) {
        ChangedAccount *c = &step->changed_accounts[i];
        account_deinit(&c->copy);
    }
    free(step->changed_accounts);
    step->changed_accounts = NULL;
}

bool
undostep_undo(UndoStep *step, AccountList *alist)
{
    if (!_remove_accounts(step->added_accounts, alist)) {
        return false;
    }
    if (!_readd_accounts(step->deleted_accounts, alist)) {
        return false;
    }
    if (!_swap_accounts(step->changed_accounts, step->changed_count)) {
        return false;
    }
    return true;
}

bool
undostep_redo(UndoStep *step, AccountList *alist)
{
    if (!_readd_accounts(step->added_accounts, alist)) {
        return false;
    }
    if (!_remove_accounts(step->deleted_accounts, alist)) {
        return false;
    }
    if (!_swap_accounts(step->changed_accounts, step->changed_count)) {
        return false;
    }
    return true;
}
