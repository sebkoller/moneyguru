#include <stdlib.h>
#include <string.h>
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

void
transaction_deinit(Transaction *txn)
{
    strfree(&txn->description);
    strfree(&txn->payee);
    strfree(&txn->checkno);
    strfree(&txn->notes);
    free(txn->splits);
}
