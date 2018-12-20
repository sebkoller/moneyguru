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
    entry->index = -1;
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
    dst->index = src->index;
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
    if (entries->count == 0) {
        dst->val = 0;
        return true;
    }
    int index;
    if (date == 0) {
        index = entries->count;
    } else {
        index = entries_find_date(entries, date, true);
    }
    // We want the entry *before* the threshold
    index--;
    if (index >= entries->count) {
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
    if (e1->index != e2->index) {
        return e1->index < e2->index ? -1 : 1;
    }
    return 0;
}

bool
entries_cook(const EntryList *ref, EntryList *tocook, Currency *currency)
{
    Amount amount;
    Amount balance;
    Amount balance_with_budget;
    Amount reconciled_balance;

    balance.currency = currency;
    balance_with_budget.currency = balance.currency;
    reconciled_balance.currency = balance.currency;
    amount.currency = balance.currency;

    if (!entries_balance(ref, &balance, 0, false)) {
        return false;
    }
    if (!entries_balance(ref, &balance_with_budget, 0, true)) {
        return false;
    }
    entries_balance_of_reconciled(ref, &reconciled_balance);
    // Entries in reconciliation order
    EntryList rel;
    rel.count = tocook->count;
    rel.entries = malloc(sizeof(Entry *) * rel.count);
    for (int i=0; i<tocook->count; i++) {
        Entry *entry = tocook->entries[i];
        entry->index = i;

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

        rel.entries[i] = entry;
    }

    qsort(rel.entries, rel.count, sizeof(Entry *), _entry_qsort_cmp);

    for (int i=0; i<rel.count; i++) {
        Entry *entry = rel.entries[i];
        if (entry->split->reconciliation_date != 0) {
            reconciled_balance.val += entry->split->amount.val;
        }
        amount_copy(&entry->reconciled_balance, &reconciled_balance);
    }
    free(rel.entries);
    return true;
}
