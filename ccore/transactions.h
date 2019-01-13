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
transactions_at_date(TransactionList *txns, time_t date);

char**
transactions_descriptions(const TransactionList *txns);

int
transactions_find(TransactionList *txns, Transaction *txn);

char**
transactions_payees(const TransactionList *txns);

bool
transactions_remove(TransactionList *txns, Transaction *txn);

void
transactions_sort(TransactionList *txns);
