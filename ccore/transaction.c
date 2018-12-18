#include "transaction.h"
#include "util.h"

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
    return true;
}
