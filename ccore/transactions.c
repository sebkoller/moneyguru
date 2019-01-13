#include <stdlib.h>
#include "transactions.h"

/* Private */
static int
_txn_cmp_key(const void *a, const void *b)
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

static int
_txn_cmp_mtime(const void *a, const void *b)
{
    Transaction *t1 = *((Transaction **)a);
    Transaction *t2 = *((Transaction **)b);

    if (t1->mtime != t2->mtime) {
        return t1->mtime < t2->mtime ? -1 : 1;
    }
    return 0;
}

// TODO: re-instate this. seems to be causing problems
// deduplicates *in place*. slist is NULL-terminated after and before.
/*static void                                                      */
/*_deduplicate_strings(char **slist)                               */
/*{                                                                */
/*    GHashTable *seen = g_hash_table_new(g_str_hash, g_str_equal);*/
/*    char **iter = slist;                                         */
/*    char **replace_iter = slist;                                 */
/*    while (*iter != NULL) {                                      */
/*        char *s = *iter;                                         */
/*        if ((s[0] != '\0') && !g_hash_table_contains(seen, &s)) {*/
/*            *replace_iter = s;                                   */
/*            g_hash_table_add(seen, &s);                          */
/*            replace_iter++;                                      */
/*        }                                                        */
/*        iter++;                                                  */
/*    }                                                            */
/*    *replace_iter = NULL;                                        */
/*    g_hash_table_destroy(seen);                                  */
/*}                                                                */

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

char**
transactions_account_names(const TransactionList *txns)
{
    Transaction **bymtime = malloc(sizeof(Transaction*) * txns->count);
    memcpy(bymtime, txns->txns, sizeof(Transaction*) * txns->count);
    qsort(bymtime, txns->count, sizeof(Transaction*), _txn_cmp_mtime);

    // we don't know our upper count limit beforehand. Let's try with
    // txns->count and realloc if needed.
    int count = txns->count;
    char **res = malloc(sizeof(char*) * count);
    int current = 0;
    for (int i=txns->count-1; i>=0; i--) {
        Account **accounts = transaction_affected_accounts(bymtime[i]);
        while (*accounts != NULL) {
            if (!(*accounts)->inactive) {
                if (current == count) {
                    // Didn't allocate enough space. double it.
                    count *= 2;
                    res = realloc(res, sizeof(char*) * count);
                }
                res[current] = (*accounts)->name;
                current++;
            }
            accounts++;
        }
    }
    res[current] = NULL;
    return res;
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
transactions_at_date(const TransactionList *txns, time_t date)
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

char**
transactions_descriptions(const TransactionList *txns)
{
    Transaction **bymtime = malloc(sizeof(Transaction*) * txns->count);
    memcpy(bymtime, txns->txns, sizeof(Transaction*) * txns->count);
    qsort(bymtime, txns->count, sizeof(Transaction*), _txn_cmp_mtime);

    char **res = malloc(sizeof(char*) * (txns->count + 1));
    char **iter = res;
    for (int i=txns->count-1; i>=0; i--) {
        *iter = bymtime[i]->description;
        if (*iter != NULL) {
            iter++;
        }
    }
    *iter = NULL;
    return res;
}

int
transactions_find(const TransactionList *txns, Transaction *txn)
{
    for (int i=0; i<txns->count; i++) {
        if (txns->txns[i] == txn) {
            return i;
        }
    }
    return -1;
}

void
transactions_move_before(
    const TransactionList *txns,
    Transaction *txn,
    Transaction *target)
{
    if (transactions_find(txns, txn) == -1) {
        return;
    }
    if ((target != NULL) && (txn->date != target->date)) {
        target = NULL;
    }
    Transaction **bunch = transactions_at_date(txns, txn->date);
    Transaction **iter = bunch;
    if (target == NULL) {
        // set txn->position to the highest value of its bunch
        while (*iter != NULL) {
            if ((*iter != txn) && ((*iter)->position >= txn->position)) {
                txn->position = (*iter)->position + 1;
            }
            iter++;
        }
    } else {
        // set txn position to its target and offset everything after it
        txn->position = target->position;
        while (*iter != NULL) {
            if ((*iter != txn) && ((*iter)->position >= txn->position)) {
                (*iter)->position++;
            }
            iter++;
        }
    }
    free(bunch);
}

char**
transactions_payees(const TransactionList *txns)
{
    Transaction **bymtime = malloc(sizeof(Transaction*) * txns->count);
    memcpy(bymtime, txns->txns, sizeof(Transaction*) * txns->count);
    qsort(bymtime, txns->count, sizeof(Transaction*), _txn_cmp_mtime);

    char **res = malloc(sizeof(char*) * (txns->count + 1));
    char **iter = res;
    for (int i=txns->count-1; i>=0; i--) {
        *iter = bymtime[i]->payee;
        if (*iter != NULL) {
            iter++;
        }
    }
    *iter = NULL;
    return res;
}

void
transactions_reassign_account(
    TransactionList *txns,
    const Account *account,
    Account *to)
{
    for (int i=txns->count-1; i>=0; i--) {
        Transaction *txn = txns->txns[i];
        if (transaction_reassign_account(txn, account, to)) {
            Account **accounts = transaction_affected_accounts(txn);
            if (accounts[0] == NULL) {
                transactions_remove(txns, txn);
            }
        }
    }
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
    qsort(txns->txns, txns->count, sizeof(Transaction*), _txn_cmp_key);
}
