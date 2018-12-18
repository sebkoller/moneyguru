#include "entry.h"

void
entry_init(Entry *entry, Split *split, Transaction *txn)
{
    entry->split = split;
    entry->txn = txn;
    amount_copy(&entry->balance, amount_zero());
    amount_copy(&entry->reconciled_balance, amount_zero());
    amount_copy(&entry->balance_with_budget, amount_zero());
    entry->index = -1;
}

void
entry_copy(Entry *dst, const Entry *src)
{
    dst->split = src->split;
    dst->txn = src->txn;
    amount_copy(&dst->balance, &src->balance);
    amount_copy(&dst->reconciled_balance, &src->reconciled_balance);
    amount_copy(&dst->balance_with_budget, &src->balance_with_budget);
    dst->index = src->index;
}
