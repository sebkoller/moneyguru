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
    int cooked_until;
    Entry **entries;
    Entry *last_reconciled;
    Account *account;
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
entries_init(EntryList *entries, Account *account);

void
entries_deinit(EntryList *entries);

bool
entries_balance(const EntryList *entries, Amount *dst, time_t date, bool with_budget);

bool
entries_balance_of_reconciled(const EntryList *entries, Amount *dst);

bool
entries_cash_flow(
    const EntryList *entries,
    Amount *dst,
    time_t from,
    time_t to);

void
entries_clear(EntryList *entries, time_t fromdate);

bool
entries_cook(EntryList *entries);

Entry*
entries_create(EntryList *entries, Split *split, Transaction *txn);

int
entries_find_date(const EntryList *entries, time_t date, bool equal);

Entry*
entries_last_entry(const EntryList *entries, time_t date);
