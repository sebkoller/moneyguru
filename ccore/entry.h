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
} Entry;

typedef struct {
    int count;
    Entry **entries;
    Entry *last_reconciled;
} EntryList;

void
entry_init(Entry *entry, Split *split, Transaction *txn);

/* Change the amount of `split`, from the perspective of the account ledger.
 *
 * This can only be done if the Transaction to which we belong is a two-way
 * transaction. This will trigger a two-way balancing with
 * `Transaction.balance`.
 *
 * Returns false if it can't proceed (if it's not a two-way entry)
 */
bool
entry_amount_set(Entry *entry, const Amount *amount);

void
entry_copy(Entry *dst, const Entry *src);

void
entries_init(EntryList *entries);

void
entries_deinit(EntryList *entries);

void
entries_add(EntryList *entries, Entry *entry);

void
entries_clear(EntryList *entries, time_t fromdate);

int
entries_find_date(const EntryList *entries, time_t date, bool equal);

bool
entries_balance(const EntryList *entries, Amount *dst, time_t date, bool with_budget);

bool
entries_balance_of_reconciled(const EntryList *entries, Amount *dst);

/* Cook entries in `tocook` in preparation to adding then in `ref`
 *
 * `ref` is a list of entries that are already cooked and `tocook` are freshly
 * created entries that will be appended to it.
 *
 * Tis function only cooks (compute running balances), it doesn't touch ref.
 */
bool
entries_cook(const EntryList *ref, EntryList *tocook, Currency *currency);
