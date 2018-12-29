#include <stdlib.h>
#include "entry.h"

void
entry_init(Entry *entry, Split *split, Transaction *txn)
{
    entry->split = split;
    entry->txn = txn;
    amount_copy(&entry->balance, amount_zero());
    amount_copy(&entry->reconciled_balance, amount_zero());
    amount_copy(&entry->balance_with_budget, amount_zero());
}

bool
entry_amount_set(Entry *entry, const Amount *amount)
{
    if (entry->txn->splitcount != 2) {
        return false;
    }
    Split *other = &entry->txn->splits[0];
    if (other == entry->split) {
        other = &entry->txn->splits[1];
    }
    split_amount_set(entry->split, amount);
    Amount *other_amount = &other->amount;
    bool is_mct = false;
    // Weird rules, but well...
    bool same_currency = amount->currency == other_amount->currency;
    if (amount->currency == NULL || other_amount->currency == NULL) {
        same_currency = true;
    }
    if (!same_currency) {
        bool is_asset = false;
        bool other_is_asset = false;
        Account *a = entry->split->account;
        if (a != NULL) {
            is_asset = account_is_balance_sheet(a);
        }
        a = other->account;
        if (a != NULL) {
            other_is_asset = account_is_balance_sheet(a);
        }
        if (is_asset && other_is_asset) {
            is_mct = true;
        }
    }

    if (is_mct) {
        // don't touch other side unless we have a logical imbalance
        if ((entry->split->amount.val > 0) == (other_amount->val > 0)) {
            Amount a;
            amount_neg(&a, other_amount);
            split_amount_set(other, &a);
        }
    } else {
        Amount a;
        amount_neg(&a, amount);
        split_amount_set(other, &a);
    }
    return true;
}

void
entry_copy(Entry *dst, const Entry *src)
{
    dst->split = src->split;
    dst->txn = src->txn;
    amount_copy(&dst->balance, &src->balance);
    amount_copy(&dst->reconciled_balance, &src->reconciled_balance);
    amount_copy(&dst->balance_with_budget, &src->balance_with_budget);
}

/* EntryList Private */
static int
_entry_qsort_cmp(const void *a, const void *b)
{
    Entry *e1 = *((Entry **)a);
    Entry *e2 = *((Entry **)b);

    time_t date1 = e1->split->reconciliation_date;
    time_t date2 = e2->split->reconciliation_date;
    if (!date1) {
        date1 = e1->txn->date;
    }
    if (!date2) {
        date2 = e2->txn->date;
    }
    if (date1 != date2) {
        return date1 < date2 ? -1 : 1;
    }
    if (e1->txn->position != e2->txn->position) {
        return e1->txn->position < e2->txn->position ? -1 : 1;
    }
    if (e1->split->index != e2->split->index) {
        return e1->split->index < e2->split->index ? -1 : 1;
    }
    return 0;
}

static void
_entries_maybe_set_last_reconciled(EntryList *entries, Entry *entry)
{
    if (entry->split->reconciliation_date != 0) {
        if (entries->last_reconciled == NULL) {
            entries->last_reconciled = entry;
        } else {
            bool replace = false;
            Entry *old = entries->last_reconciled;
            if (entry->split->reconciliation_date != old->split->reconciliation_date) {
                if (entry->split->reconciliation_date > old->split->reconciliation_date) {
                    replace = true;
                }
            } else if (entry->txn->date != old->txn->date) {
                if (entry->txn->date > old->txn->date) {
                    replace = true;
                }
            } else if (entry->txn->position != old->txn->position) {
                if (entry->txn->position > old->txn->position) {
                    replace = true;
                }
            } else if (entry->split->index > old->split->index) {
                replace = true;
            }
            if (replace) {
                entries->last_reconciled = entry;
            }
        }
    }
}

/* EntryList Public*/
void
entries_init(EntryList *entries, Account *account)
{
    entries->count = 0;
    entries->cooked_until = 0;
    entries->entries = NULL;
    entries->last_reconciled = NULL;
    entries->account = account;
}

void
entries_deinit(EntryList *entries)
{
    free(entries->entries);
}

Entry*
entries_create(EntryList *entries, Split *split, Transaction *txn)
{
    entries->count++;
    entries->entries = realloc(
        entries->entries,
        sizeof(Entry*) * entries->count);
    Entry *res = malloc(sizeof(Entry));
    entry_init(res, split, txn);
    entries->entries[entries->count-1] = res;
    return res;
}

void
entries_clear(EntryList *entries, time_t fromdate)
{
    int index;
    if (fromdate == 0) {
        index = 0;
    } else {
        index = entries_find_date(entries, fromdate, false);
        if (index >= entries->count) {
            // Everything is smaller, don't clear anything.
            return;
        }
    }
    entries->count = index;
    entries->cooked_until = index;
    entries->entries = realloc(
        entries->entries,
        sizeof(Entry*) * entries->count);
    entries->last_reconciled = NULL;
    for (int i=0; i<index; i++) {
        _entries_maybe_set_last_reconciled(entries, entries->entries[i]);
    }
}

int
entries_find_date(const EntryList *entries, time_t date, bool equal)
{
    // equal=true: find index with closest smaller-or-equal date to "date"
    // equal=false: find smaller only
    // Returns the index *following* the nearest result. Returned index goes
    // over the threshold.
    if (entries->count == 0) {
        return 0;
    }
    int low = 0;
    int high = entries->count - 1;
    bool matched_once = false;
    while ((high > low) || ((high == low) && !matched_once)) {
        int mid = ((high - low) / 2) + low;
        Entry *entry = entries->entries[mid];
        time_t tdate = entry->txn->date;
        // operator *look* like they're inverted, but they're not.
        bool match = equal ? tdate > date : tdate >= date;
        if (match) {
            matched_once = true;
            high = mid;
        } else {
            low = mid + 1;
        }
    }
    if (matched_once) {
        // we have at least one entry with a higher date than "date"
        return (int)high;
    } else {
        // All entries have a smaller date than "date". Return len.
        return entries->count;
    }

}

bool
entries_balance(const EntryList *entries, Amount *dst, time_t date, bool with_budget)
{
    if (entries->cooked_until == 0) {
        dst->val = 0;
        return true;
    }
    int index;
    if (date == 0) {
        index = entries->cooked_until;
    } else {
        index = entries_find_date(entries, date, true);
    }
    // We want the entry *before* the threshold
    index--;
    if (index >= entries->cooked_until) {
        // Something's wrong
        return false;
    }
    if (index >= 0) {
        Entry *entry = entries->entries[index];
        Amount *src = with_budget ? &entry->balance_with_budget : &entry->balance;
        if (date > 0) {
            if (amount_convert(dst, src, date)) {
                return true;
            } else {
                return false;
            }
        } else {
            amount_copy(dst, src);
            return true;
        }
    } else {
        dst->val = 0;
        return true;
    }
}

bool
entries_balance_of_reconciled(const EntryList *entries, Amount *dst)
{
    if (entries->last_reconciled == NULL) {
        dst->val = 0;
        return false;
    } else {
        amount_copy(dst, &entries->last_reconciled->reconciled_balance);
        return true;
    }
}

bool
entries_cook(EntryList *entries)
{
    int cookcount = entries->count - entries->cooked_until;
    if (!cookcount) {
        // nothing to cook
        return true;
    }
    Amount amount;
    Amount balance;
    Amount balance_with_budget;
    Amount reconciled_balance;

    if (!entries_balance(entries, &balance, 0, false)) {
        return false;
    }
    if (!entries_balance(entries, &balance_with_budget, 0, true)) {
        return false;
    }
    entries_balance_of_reconciled(entries, &reconciled_balance);
    balance.currency = entries->account->currency;
    balance_with_budget.currency = balance.currency;
    reconciled_balance.currency = balance.currency;
    amount.currency = balance.currency;

    // Entries in reconciliation order
    Entry** rel;
    rel = malloc(sizeof(Entry *) * cookcount);
    for (int i=0; i<cookcount; i++) {
        Entry *entry = entries->entries[entries->cooked_until+i];
        Split *split = entry->split;
        if (!amount_convert(&amount, &split->amount, entry->txn->date)) {
            return false;
        }
        if (entry->txn->type != TXN_TYPE_BUDGET) {
            balance.val += amount.val;
        }
        amount_copy(&entry->balance, &balance);
        balance_with_budget.val += amount.val;
        amount_copy(&entry->balance_with_budget, &balance_with_budget);

        rel[i] = entry;
    }

    qsort(rel, cookcount, sizeof(Entry *), _entry_qsort_cmp);

    for (int i=0; i<cookcount; i++) {
        Entry *entry = rel[i];
        if (entry->split->reconciliation_date != 0) {
            reconciled_balance.val += entry->split->amount.val;
            entries->last_reconciled = entry;
        }
        amount_copy(&entry->reconciled_balance, &reconciled_balance);
    }
    free(rel);
    entries->cooked_until = entries->count;
    return true;
}
