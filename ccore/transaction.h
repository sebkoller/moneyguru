#pragma once
#include <time.h>
#include <stdbool.h>
#include "split.h"

typedef enum {
    TXN_TYPE_NORMAL = 1,
    TXN_TYPE_RECURRENCE = 2,
    TXN_TYPE_BUDGET = 3,
} TransactionType;

/* A movement of money between two or more accounts at a specific date.
 * 
 * Money movements that a transaction implies are listed in `splits`. The
 * splits of a transaction *always balance*, which means that the sum of
 * amounts in its splits is always zero.
 * 
 * Whenever a potentially unbalancing operation is made on the splits, call
 * `transaction_balance()` to balance the transaction out.
 *
 * SPAWNS
 *
 * Transactions of type RECURRENCE and BUDGET are called "spawns". Spawns are
 * instances of a recurrent transaction at a specific date.
 *
 * Recurrences are transactions that are repeated multiple times. Spawns are
 * specific occurrences of a schedule. It's the spawn, not the schedule, that
 * will end up showing up in the transaction list with the little clock icon
 * next to it.
 *
 * Other than holding a reference to its recurrence, it behaves pretty much
 * like a normal transaction.
 */
typedef struct _Transaction {
    TransactionType type;
    // Date at which the transation occurs.
    time_t date;
    // Description of the transaction.
    char *description;
    // Person or entity related to the transaction.
    char *payee;
    // Check number related to the transaction.
    char *checkno;
    // Freeform note about the transaction.
    char *notes;
    // Ordering attributes. When two transactions have the same date, we order
    // them with this.
    int position;
    // Timestamp of the last modification. Used in the UI to let the user sort
    // his transactions.  This is useful for finding a mistake that we know was
    // introduced recently.
    time_t mtime;
    // Splits belonging to that txn. The transaction owns the splits and the
    // list is never over-allocated. This means that all splits are "valid".
    Split *splits;
    unsigned int splitcount;
    // Used to hold the result of transaction_affected_accounts(). Is
    // reinitialized on each call and freed on transaction_deinit().
    Account **affected_accounts;

    // Recurrence-related fields
    struct _Transaction *ref;
    time_t recurrence_date;
} Transaction;

void
transaction_init(Transaction *txn, TransactionType type, time_t date);

void
transaction_deinit(Transaction *txn);

Split*
transaction_add_split(Transaction *txn);

/* Returns a NULL-terminated list of all accounts affected by txn.
 *
 * ... meaning all accounts references by our splits. Returned list is managed
 * by the transaction itself. Do not free. Do not keep around either, will be
 * overwritten/reallocated on next call.
 */
Account**
transaction_affected_accounts(Transaction *txn);

/* Total amount of the transaction, that is, the absolute sum of all splits,
 * divided by 2. If `txn` is a multi-currency txn, result is converted to the
 * currency of the first split.
 */
bool
transaction_amount(const Transaction *txn, Amount *dest);

/* Assigns remaining imbalance to the selected split.
 *
 * If the `target` is not an assigned split, does nothing.
 *
 * Returns whether an assignation was done.
 */
bool
transaction_assign_imbalance(Transaction *txn, Split *target);

/* Returns the total sum attributed to `account`.
 * 
 * All amounts are converted to `dest->currency` (which must be set) before
 * doing the sum. This is needed because we might have amounts with different
 * currencies here.
 */
void
transaction_amount_for_account(
    const Transaction *txn,
    Amount *dest,
    const Account *account);

/* Balances a multi-currency transaction.
 * 
 * Balancing out multi-currencies transasctions can be real easy because we
 * consider that currencies can never mix (and we would never make the gross
 * mistake of using market exchange rates to do our balancing), so, if we have
 * at least one split on each side of different currencies, we consider
 * ourselves balanced and do nothing.
 * 
 * However, we might be in a situation of "logical imbalance", which means that
 * the transaction doesn't logically makes sense. For example, if all our
 * splits are on the same side, we can't possibly balance out. If we have EUR
 * and CAD splits, that CAD splits themselves balance out but that EUR splits
 * are all on the same side, we have a logical imbalance.
 * 
 * This method finds those imbalance and fix them by creating unsassigned
 * splits balancing out every currency being in that situation.
 * 
 * `strong_split` is the split that was last edited (can be `NULL`). See
 * balance() for details.
 */
void
transaction_balance_currencies(Transaction *txn, const Split *strong_split);

/* Balance out `splits` if needed.
 * 
 * A balanced transaction has all its splits making a zero sum. Balancing a
 * transaction is rather easy: We sum all our splits and create an unassigned
 * split of the opposite of that amount. To avoid polluting our splits, we look
 * if we already have an unassigned split and, if we do, we adjust its amount
 * instead of creating a new split.
 * 
 * There's a special case to that rule, and that is when we have two splits.
 * When those two splits are on the same "side" (both positive or both
 * negative), we assume that the user has just reversed `strong_split`'s side
 * and that the logical next step is to also reverse the other split (the
 * "weak" split), which we'll do.
 * 
 * If `keep_two_splits` is true, we'll go one step further and adjust the weak
 * split's amount to fit what was just entered in the strong split. If it's
 * false, we'll create an unassigned split if needed.
 * 
 * Easy, right? Things get a bit more complicated when a have a multi-currency
 * transaction. When that happens, we do a more complicated balancing, which
 * happens in `transaction_balance_currencies()`.
 * 
 * `strong_split` is the split that was last edited. The reason why we're
 * balancing the transaction now. If set, it will not be adjusted by the
 * balancing because we don't want to pull the rug from under our user's feet
 * and undo an edit she's just made.
 */
void
transaction_balance(
    Transaction *txn,
    Split *strong_split,
    bool keep_two_splits);

// Whether we have two or less splits of the same currency.
bool
transaction_can_set_amount(const Transaction *txn);

int
transaction_cmp(const Transaction *a, const Transaction *b);

// If dst is a fresh instance, it *has* to have been zeroed out before calling
// this.
bool
transaction_copy(Transaction *dst, Transaction *src);

// Returns whether splits hold more than one currency
bool
transaction_is_mct(const Transaction *txn);

// Whether our splits all have null amounts.
bool
transaction_is_null(const Transaction *txn);

/* Balances a multi-currency transaction using exchange rates.
 *
 * *This balancing doesn't occur automatically, it is a user-initiated action.*
 * 
 * Sums up the value of all splits in `new_split_currency`, using exchange
 * rates for `txn.date`. If not zero, create a new unassigned split with the
 * opposite of that amount.
 * 
 * Of course, we need to have called `transaction_balance()` before we can call
 * this.
 */
void
transaction_mct_balance(Transaction *txn, Currency *new_split_currency);

bool
transaction_move_split(Transaction *txn, Split *split, unsigned int newindex);

// For debugging
void
transaction_print(const Transaction *txn);

/* Reassign all splits from `account` to `reassign_to`.
 *
 * All splits belonging to `account` will be changed to `to`.
 *
 * Returns whether any change was made.
 */
bool
transaction_reassign_account(
    Transaction *txn,
    const Account *account,
    Account *to);

bool
transaction_remove_split(Transaction *txn, Split *split);

// Reallocate split array to `newsize`. If larger than the old splitcount, new
// splits are initialized to NULL account and zero amount.
void
transaction_resize_splits(Transaction *txn, unsigned int newsize);

