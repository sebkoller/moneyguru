#pragma once
#include "transaction.h"

typedef struct {
    unsigned int count;
    Transaction **txns;
} TransactionList;

void
transactions_init(TransactionList *txns);

void
transactions_deinit(TransactionList *txns);

char**
transactions_account_names(const TransactionList *txns);

/* keep_position: if true, `txn`'s `position` stays unchanged. if false, we
 *                set `position` so that `txn` ends up at the end of the txns
 *                that are on the same date.
 */
void
transactions_add(TransactionList *txns, Transaction *txn, bool keep_position);

/* Returns a NULL-terminated list of txns with specified date
 *
 * The resulting list must be freed with free(). Returns NULL if there's no
 * matching txn.
 */
Transaction**
transactions_at_date(const TransactionList *txns, time_t date);

char**
transactions_descriptions(const TransactionList *txns);

int
transactions_find(const TransactionList *txns, Transaction *txn);

/* Move `txn` just before `target`, position-wise.
 *
 * Sets the `position` attribute of `txn` so that it ends up directly before
 * `target`. This usually implies changing the position of all following txns
 * on the same day.
 *
 * If `target` is NULL, `txn` is placed at the end of the bunch of txns on the
 * same date.
 *
 * If `txn` and `target` don't have the same date, `target` is considered NULL.
 */
void
transactions_move_before(
    const TransactionList *txns,
    Transaction *txn,
    Transaction *target);

char**
transactions_payees(const TransactionList *txns);

/* Calls `transaction_reassign_account()` on all transactions.
 *
 * If, after such an operation, a transaction ends up referencing no account at
 * all, it is removed.
 */
void
transactions_reassign_account(
    TransactionList *txns,
    const Account *account,
    Account *to);

bool
transactions_remove(TransactionList *txns, Transaction *txn);

void
transactions_sort(TransactionList *txns);
