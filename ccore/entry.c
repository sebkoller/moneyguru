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

int
entries_find_date(EntryList *entries, time_t date, bool equal)
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
