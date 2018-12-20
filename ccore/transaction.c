#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "transaction.h"
#include "util.h"

/* Private */
static bool
_txn_check_ownership(Transaction *txn, Split *split)
{
    if (split->index >= txn->splitcount) {
        // out of bounds
        return false;
    }
    if (split != &txn->splits[split->index]) {
        // not part of this txn
        return false;
    }
    return true;
}

static void
_txn_reindex(Transaction *txn)
{
    for (unsigned int i=0; i<txn->splitcount; i++) {
        txn->splits[i].index = i;
    }
}

// Currencies involved in this txn. Null terminated.
// Caller is responsible for freeing list
Currency**
_txn_currencies(const Transaction *txn)
{
    Currency **res = calloc((txn->splitcount + 1), sizeof(Currency *));
    for (unsigned int i=0; i<txn->splitcount; i++) {
        Currency *c = txn->splits[i].amount.currency;
        if (c == NULL) {
            continue;
        }
        Currency **iter = res;
        while (1) {
            if (*iter == c) {
                break;
            } else if (*iter == NULL) {
                *iter = c;
                break;
            } else {
                iter++;
            }
        }
    }
    return res;
}

// Set result's currency to specify target currency
static void
_txn_balance_for_currency(const Transaction *txn, Amount *result)
{
    if (result->currency == NULL) {
        return;
    }
    result->val = 0;
    for (unsigned int i=0; i<txn->splitcount; i++) {
        const Split *s = &txn->splits[i];
        if (s->amount.currency == result->currency) {
            result->val += s->amount.val;
        }
    }

}

static Split*
_txn_find_unassigned(Transaction *txn, Currency *c, int except_index)
{
    for (unsigned int i=0; i<txn->splitcount; i++) {
        if (i == except_index) continue;
        Split *s = &txn->splits[i];
        if (s->account == NULL
            && (s->amount.currency == c || s->amount.currency == NULL)) {
            return s;
        }
    }
    return NULL;
}

static void
_txn_assign_imbalance(
    Transaction *txn,
    const Amount *imbalance,
    int except_index)
{
    Split *target = _txn_find_unassigned(txn, imbalance->currency, except_index);
    if (target == NULL) {
        // no existing target, let's create one
        target = transaction_add_split(txn);
    }
    // target could be a NULL split.
    target->amount.currency = imbalance->currency;
    target->amount.val -= imbalance->val;
    if (target->amount.val == 0) {
        // We end up with an empty split, remove it
        transaction_remove_split(txn, target);
    }
}
/* Public */
void
transaction_init(Transaction *txn, TransactionType type, time_t date)
{
    txn->type = type;
    txn->date = date;
    txn->description = "";
    txn->payee = "";
    txn->checkno = "";
    txn->notes = "";
    txn->position = 0;
    txn->mtime = 0;
    txn->splits = malloc(0);
    txn->splitcount = 0;
}

void
transaction_deinit(Transaction *txn)
{
    strfree(&txn->description);
    strfree(&txn->payee);
    strfree(&txn->checkno);
    strfree(&txn->notes);
    free(txn->splits);
}

Split*
transaction_add_split(Transaction *txn)
{
    transaction_resize_splits(txn, txn->splitcount+1);
    return &txn->splits[txn->splitcount-1];
}

void
transaction_balance_currencies(Transaction *txn, const Split *strong_split)
{
    // What we're doings here is that we solve a logical imbalance. First, we
    // need to confirm the logical imbalance by verifying that all imbalanced
    // currencies are on the same "side".

    Currency **currencies = _txn_currencies(txn);
    Currency **iter = currencies;
    Amount prev;
    Amount bal;
    amount_set(&prev, 0, NULL);
    while (*iter != NULL) {
        bal.currency = *iter;
        _txn_balance_for_currency(txn, &bal);
        if (bal.val != 0) {
            if (prev.val != 0 && !amount_same_side(&prev, &bal)) {
                // We have imbalances, but on different sides. We don't
                // have anything to do.
                free(currencies);
                return;
            }
            amount_copy(&prev, &bal);
        }
        iter++;
    }
    if (prev.val == 0) {
        // We have no imbalance
        free(currencies);
        return;
    }
    // At this point, we know that we have imbalances and that those imbalances
    // are all on the same "side". Let's rebalance them.
    iter = currencies;
    // strong_split might become invalid in the loop below.
    int except_index = strong_split != NULL ? strong_split->index : -1;
    amount_set(&prev, 0, NULL);
    while (*iter != NULL) {
        bal.currency = *iter;
        _txn_balance_for_currency(txn, &bal);
        if (bal.val != 0) {
            _txn_assign_imbalance(txn, &bal, except_index);
        }
        iter++;
    }
    free(currencies);
}

void
transaction_balance(
    Transaction *txn,
    Split *strong_split,
    bool keep_two_splits)
{
    if (txn->splitcount == 0) {
        return;
    }
    if (txn->splitcount == 2 && strong_split != NULL) {
        Split *weak = &txn->splits[0];
        if (weak == strong_split) {
            weak = &txn->splits[1];
        }
        if (keep_two_splits) {
            amount_neg(&weak->amount, &strong_split->amount);
            return;
        }
        if (amount_same_side(&weak->amount, &strong_split->amount)) {
            weak->amount.val *= -1;
        }
    }
    Currency **currencies = _txn_currencies(txn);
    // Because we have more than 0 splits, currencies has at the very least 2
    // items, so the check below is safe.
    bool mct = currencies[1] != NULL;
    Amount bal;
    amount_set(&bal, 0, currencies[0]);
    free(currencies);
    if (mct) {
        transaction_balance_currencies(txn, strong_split);
        return;
    }
    if (bal.currency != NULL) {
        _txn_balance_for_currency(txn, &bal);
    }
    if (bal.val != 0) {
        int except_index = strong_split != NULL ? strong_split->index : -1;
        _txn_assign_imbalance(txn, &bal, except_index);
    }
    // And, finally, cleanup
    for (int i=txn->splitcount-1; i>=0; i--) {
        Split *s = &txn->splits[i];
        if (s != strong_split && s->amount.val == 0 && s->account == NULL) {
            transaction_remove_split(txn, s);
        }
    }
}

int
transaction_cmp(const Transaction *a, const Transaction *b)
{
    if (a->date != b->date) {
        return a->date > b->date ? 1 : -1;
    } else if (a->position != b->position) {
        return a->position > b->position ? 1 : -1;
    }
    return 0;
}

bool
transaction_copy(Transaction *dst, Transaction *src)
{
    if (dst == src) {
        // not supposed to be tried
        return false;
    }
    dst->type = src->type;
    dst->date = src->date;
    if (!strclone(&dst->description, src->description)) {
        return false;
    }
    if (!strclone(&dst->payee, src->payee)) {
        return false;
    }
    if (!strclone(&dst->checkno, src->checkno)) {
        return false;
    }
    if (!strclone(&dst->notes, src->notes)) {
        return false;
    }
    dst->position = src->position;
    dst->mtime = src->mtime;
    dst->splitcount = src->splitcount;
    dst->splits = malloc(sizeof(Split) * dst->splitcount);
    memset(dst->splits, 0, sizeof(Split) * dst->splitcount);
    for (unsigned int i=0; i<dst->splitcount; i++) {
        if (!split_copy(&dst->splits[i], &src->splits[i])) {
            return false;
        }
    }
    _txn_reindex(dst);
    return true;
}

bool
transaction_move_split(Transaction *txn, Split *split, unsigned int newindex)
{
    if (!_txn_check_ownership(txn, split)) {
        return false;
    }
    if (newindex >= txn->splitcount) {
        return false;
    }
    if (newindex == split->index) {
        return true;
    }

    unsigned int index = split->index;
    Split copy;
    memcpy(&copy, split, sizeof(Split));
    if (newindex > index) {
        // Shift splits in between to the left
        memmove(
            &txn->splits[index],
            &txn->splits[index+1],
            sizeof(Split) * (newindex - index));
    } else {
        // Shift splits in between to the right
        memmove(
            &txn->splits[newindex+1],
            &txn->splits[newindex],
            sizeof(Split) * (index - newindex));
    }
    memcpy(&txn->splits[newindex], &copy, sizeof(Split));
    _txn_reindex(txn);
    return true;
}

void
transaction_print(const Transaction *txn)
{
    printf("Splits: %d\n", txn->splitcount);
    for (unsigned int i=0; i<txn->splitcount; i++) {
        Split *s = &txn->splits[i];
        printf("  - %s %ld %s\n",
            s->account == NULL ? "(None)" : s->account->name,
            s->amount.val,
            s->amount.currency == NULL ? "(None)" : s->amount.currency->code);
    }
}

bool
transaction_remove_split(Transaction *txn, Split *split)
{
    if (!_txn_check_ownership(txn, split)) {
        return false;
    }
    unsigned int count = txn->splitcount;
    unsigned int index = split->index;
    if (index < count-1) {
        // we have to move memory around
        memmove(
            &txn->splits[index],
            &txn->splits[index+1],
            sizeof(Split) * (count - index - 1));
    }
    _txn_reindex(txn);
    transaction_resize_splits(txn, count-1);
    return true;
}

// Reallocate split array to `newsize`. If larger than the old splitcount, new
// splits are initialized to NULL account and zero amount.
void
transaction_resize_splits(Transaction *txn, unsigned int newsize)
{
    if (newsize == txn->splitcount) {
        return;
    }
    txn->splits = realloc(txn->splits, sizeof(Split) * newsize);
    for (unsigned int i=txn->splitcount; i<newsize; i++) {
        split_init(&txn->splits[i], NULL, amount_zero(), i);
    }
    txn->splitcount = newsize;
}
