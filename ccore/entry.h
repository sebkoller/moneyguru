#pragma once

#include "amount.h"
#include "split.h"
#include "transaction.h"

/* An Entry represents a split in the context of an account */
typedef struct {
    // The split that we wrap
    Split *split;
    // The txn it's associated to
    Transaction *txn;
    // The running total of all preceding entries in the account.
    Amount balance;
    // The running total of all preceding *reconciled* entries in the account.
    Amount reconciled_balance;
    // Running balance which includes all Budget spawns.
    Amount balance_with_budget;
    // Index in the EntryList. Set by `EntryList.add_entry` and used as a tie
    // breaker in case we have more than one entry from the same transaction.
    int index;
} Entry;

typedef struct {
    int count;
    Entry **entries;
    Entry *last_reconciled;
} EntryList;

void
entry_init(Entry *entry, Split *split, Transaction *txn);

void
entry_copy(Entry *dst, const Entry *src);

int
entries_find_date(EntryList *entries, time_t date, bool equal);

bool
entries_balance(EntryList *entries, Amount *dst, time_t date, bool with_budget);

bool
entries_balance_of_reconciled(EntryList *entries, Amount *dst);
