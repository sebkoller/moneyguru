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

void
transactions_add(TransactionList *txns, Transaction *txn);

int
transactions_find(TransactionList *txns, Transaction *txn);

bool
transactions_remove(TransactionList *txns, Transaction *txn);

void
transactions_sort(TransactionList *txns);
