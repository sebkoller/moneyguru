#include "split.h"
#include "util.h"

void
split_init(Split *split, Account *account, const Amount *amount)
{
    split->account = account;
    amount_copy(&split->amount, amount);
    split->reconciliation_date = 0;
    split->memo = "";
    split->reference = NULL;
}

void
split_account_set(Split *split, Account *account)
{
    if (account != split->account) {
        split->reconciliation_date = 0;
        split->account = account;
    }
}

void
split_amount_set(Split *split, const Amount *amount)
{
    if (split->amount.currency && amount->currency != split->amount.currency) {
        split->reconciliation_date = 0;
    }
    amount_copy(&split->amount, amount);
}

bool
split_copy(Split *dst, const Split *src)
{
    dst->account = src->account;
    amount_copy(&dst->amount, &src->amount);
    dst->reconciliation_date = src->reconciliation_date;
    if (!strclone(&dst->memo, src->memo)) {
        return false;
    }
    if (!strclone(&dst->reference, src->reference)) {
        return false;
    }
    return true;
}

void
split_deinit(Split *split)
{
    strfree(&split->memo);
    strfree(&split->reference);
}
