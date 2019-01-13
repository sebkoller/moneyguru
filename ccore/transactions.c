#include "transactions.h"

/* Private */
static int
_txn_qsort_cmp(const void *a, const void *b)
{
    Transaction *t1 = *((Transaction **)a);
    Transaction *t2 = *((Transaction **)b);

    if (t1->date != t2->date) {
        return t1->date < t2->date ? -1 : 1;
    }
    if (t1->position != t2->position) {
        return t1->position < t2->position ? -1 : 1;
    }
    return 0;
}

/* Public */
void
transactions_init(TransactionList *txns)
{
    txns->count = 0;
    txns->txns = NULL;
}

void
transactions_deinit(TransactionList *txns)
{
    /*for (int i=0; i<txns->count; i++) {  */
    /*    Transaction *txn = txns->txns[i];*/
    /*    transaction_deinit(txn);         */
    /*    free(txn);                       */
    /*}                                    */
    free(txns->txns);
}

void
transactions_add(TransactionList *txns, Transaction *txn, bool keep_position)
{
    if (!keep_position) {
        Transaction **others = transactions_at_date(txns, txn->date);
        if (others != NULL) {
            Transaction **iter = others;
            while (*iter != NULL) {
                if ((*iter)->position >= txn->position) {
                    txn->position = (*iter)->position + 1;
                }
                iter++;
            }
            free(others);
        }
    }
    txns->count++;
    txns->txns = realloc(txns->txns, sizeof(Transaction*) * txns->count);
    txns->txns[txns->count-1] = txn;
}

Transaction**
transactions_at_date(TransactionList *txns, time_t date)
{
    /* We don't (yet) maintain sort order at all times, so we have to iterate
     * through the whole list. However, most of the time, all resulting txns
     * will be bunched up together. Because we don't know how many elements we
     * need to allocate yet, we start with a first pass, to get first/last
     * indexes and count. This then allows us to allocate and, with first/last,
     * make the second pass usually much faster.
     */
    int first, last, count=0;
    for (int i=0; i<txns->count; i++) {
        if (txns->txns[i]->date == date) {
            last = i;
            if (count == 0) {
                first = i;
            }
            count++;
        }
    }
    if (count == 0) {
        return NULL;
    }
    Transaction** res = malloc(sizeof(Transaction*) * (count+1));
    int fillindex = 0;
    for (int i=first; i<=last; i++) {
        if (txns->txns[i]->date == date) {
            res[fillindex] = txns->txns[i];
            fillindex++;
        }
    }
    res[count] = NULL;
    return res;
}

int
transactions_find(TransactionList *txns, Transaction *txn)
{
    for (int i=0; i<txns->count; i++) {
        if (txns->txns[i] == txn) {
            return i;
        }
    }
    return -1;
}

bool
transactions_remove(TransactionList *txns, Transaction *txn)
{
    int index = transactions_find(txns, txn);
    if (index == -1) {
        // bad pointer
        return false;
    }
    // we have to move memory around
    memmove(
        &txns->txns[index],
        &txns->txns[index+1],
        sizeof(Transaction*) * (txns->count - index - 1));
    txns->count--;
    txns->txns = realloc(txns->txns, sizeof(Transaction*) * txns->count);
    return true;
}

void
transactions_sort(TransactionList *txns)
{
    qsort(txns->txns, txns->count, sizeof(Transaction*), _txn_qsort_cmp);
}
