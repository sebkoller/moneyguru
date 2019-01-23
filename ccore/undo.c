#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "undo.h"
#include "util.h"

/* Private */
static bool
_remove_accounts(Account **accounts, AccountList *alist)
{
    if (accounts == NULL) {
        return true;
    }
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
    if (accounts == NULL) {
        return true;
    }
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

static void
_add_auto_created_accounts(Transaction *txn, AccountList *alist)
{
    for (int i=0; i<txn->splitcount; i++) {
        Split *split = &txn->splits[i];
        if (split->account == NULL) {
            continue;
        }
        // TODO: replace this by some kind of undelete: pretty much certain to
        // be in alist's trash can.
        if (accounts_find_by_name(alist, split->account->name) == NULL) {
            Account *a = accounts_create(alist);
            account_copy(a, split->account);
        }
    }
}

static void
_remove_auto_created_account(Transaction *txn, AccountList *alist)
{
    for (int i=0; i<txn->splitcount; i++) {
        Split *split = &txn->splits[i];
        if (split->account == NULL || !split->account->autocreated) {
            continue;
        }
        EntryList *el = accounts_entries_for_account(alist, split->account);
        if (el->count <= 1) {
            Account *a = accounts_find_by_name(alist, split->account->name);
            if (a != NULL) {
                accounts_remove(alist, a);
            }
        }
    }
}

static bool
_remove_txns(Transaction **txns, TransactionList *tlist, AccountList *alist)
{
    if (txns == NULL) {
        return true;
    }
    while (*txns != NULL) {
        if (!transactions_remove(tlist, *txns)) {
            return false;
        }
        _remove_auto_created_account(*txns, alist);
        txns++;
    }
    return true;
}

static bool
_readd_txns(Transaction **txns, TransactionList *tlist, AccountList *alist)
{
    if (txns == NULL) {
        return true;
    }
    while (*txns != NULL) {
        transactions_add(tlist, *txns, true);
        _add_auto_created_accounts(*txns, alist);
        txns++;
    }
    return true;
}

static bool
_swap_txns(ChangedTransaction *txns, int count, AccountList *alist)
{
    for (int i=0; i<count; i++) {
        ChangedTransaction *c = &txns[i];
        Transaction tmp;
        if (c->txn == NULL) {
            return false;
        }
        _remove_auto_created_account(c->txn, alist);
        // We don't use transaction_copy() because we don't have to mess with
        // string or split ownership: these ownerships follow cleanly with a
        // simple memcpy().
        memcpy(&tmp, c->txn, sizeof(Transaction));
        memcpy(c->txn, &c->copy, sizeof(Transaction));
        memcpy(&c->copy, &tmp, sizeof(Transaction));
        _add_auto_created_accounts(c->txn, alist);
    }
    return true;
}

/* Public */
void
undostep_init(
    UndoStep *step,
    Account **added_accounts,
    Account **deleted_accounts,
    Account **changed_accounts,
    Transaction **added_txns,
    Transaction **deleted_txns,
    Transaction **changed_txns)
{
    int count;
    count = listlen((void *)added_accounts);
    if (count) {
        step->added_accounts = malloc(sizeof(Account*) * (count + 1));
        memcpy(step->added_accounts, added_accounts, sizeof(Account*) * (count + 1));
    } else {
        step->added_accounts = NULL;
    }
    count = listlen((void *)deleted_accounts);
    if (count) {
        step->deleted_accounts = malloc(sizeof(Account*) * (count + 1));
        memcpy(step->deleted_accounts, deleted_accounts, sizeof(Account*) * (count + 1));
    } else {
        step->deleted_accounts = NULL;
    }
    step->changed_account_count = listlen((void *)changed_accounts);
    step->changed_accounts = calloc(sizeof(ChangedAccount), step->changed_account_count);
    for (int i=0; i<step->changed_account_count; i++) {
        ChangedAccount *c = &step->changed_accounts[i];
        c->account = changed_accounts[i];
        account_copy(&c->copy, c->account);
    }

    count = listlen((void *)added_txns);
    if (count) {
        step->added_txns = malloc(sizeof(Transaction*) * (count + 1));
        memcpy(step->added_txns, added_txns, sizeof(Transaction*) * (count + 1));
    } else {
        step->added_txns = NULL;
    }
    count = listlen((void *)deleted_txns);
    if (count) {
        step->deleted_txns = malloc(sizeof(Transaction*) * (count + 1));
        memcpy(step->deleted_txns, deleted_txns, sizeof(Transaction*) * (count + 1));
    } else {
        step->deleted_txns = NULL;
    }
    step->changed_txns_count = listlen((void *)changed_txns);
    step->changed_txns = calloc(sizeof(ChangedTransaction), step->changed_txns_count);
    for (int i=0; i<step->changed_txns_count; i++) {
        ChangedTransaction *c = &step->changed_txns[i];
        c->txn = changed_txns[i];
        transaction_copy(&c->copy, c->txn);
    }
}

void
undostep_deinit(UndoStep *step)
{
    free(step->added_accounts);
    step->added_accounts = NULL;
    free(step->deleted_accounts);
    step->deleted_accounts = NULL;
    for (int i=0; i<step->changed_account_count; i++) {
        ChangedAccount *c = &step->changed_accounts[i];
        account_deinit(&c->copy);
    }
    free(step->changed_accounts);
    step->changed_accounts = NULL;
    for (int i=0; i<step->changed_txns_count; i++) {
        ChangedTransaction *c = &step->changed_txns[i];
        transaction_deinit(&c->copy);
    }
    free(step->changed_txns);
    step->changed_txns = NULL;
}

bool
undostep_undo(UndoStep *step, AccountList *alist, TransactionList *tlist)
{
    if (!_remove_accounts(step->added_accounts, alist)) {
        return false;
    }
    if (!_readd_accounts(step->deleted_accounts, alist)) {
        return false;
    }
    if (!_swap_accounts(step->changed_accounts, step->changed_account_count)) {
        return false;
    }
    if (!_remove_txns(step->added_txns, tlist, alist)) {
        return false;
    }
    if (!_readd_txns(step->deleted_txns, tlist, alist)) {
        return false;
    }
    if (!_swap_txns(step->changed_txns, step->changed_txns_count, alist)) {
        return false;
    }
    return true;
}

bool
undostep_redo(UndoStep *step, AccountList *alist, TransactionList *tlist)
{
    if (!_readd_accounts(step->added_accounts, alist)) {
        return false;
    }
    if (!_remove_accounts(step->deleted_accounts, alist)) {
        return false;
    }
    if (!_swap_accounts(step->changed_accounts, step->changed_account_count)) {
        return false;
    }
    if (!_readd_txns(step->added_txns, tlist, alist)) {
        return false;
    }
    if (!_remove_txns(step->deleted_txns, tlist, alist)) {
        return false;
    }
    if (!_swap_txns(step->changed_txns, step->changed_txns_count, alist)) {
        return false;
    }
    return true;
}
