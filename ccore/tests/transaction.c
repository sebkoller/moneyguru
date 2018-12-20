#include <CUnit/CUnit.h>
#include "../transaction.h"
#include "../account.h"
#include "../currency.h"

static void test_remove_split()
{
    Transaction t;
    transaction_init(&t, TXN_TYPE_NORMAL, 42);
    transaction_resize_splits(&t, 3);
    t.splits[0].amount.val = 43;
    t.splits[1].amount.val = 44;
    t.splits[2].amount.val = 45;
    Split *toremove = &t.splits[1];
    CU_ASSERT(transaction_remove_split(&t, toremove));
    CU_ASSERT(t.splitcount == 2);
    CU_ASSERT(t.splits[1].amount.val == 45);
    // Calling it again will remove the second split again
    CU_ASSERT(transaction_remove_split(&t, toremove));
    CU_ASSERT(t.splitcount == 1);
    CU_ASSERT(t.splits[0].amount.val == 43);
    // But now, the call results in trying to remove an out of bounds split and
    // fails.
    CU_ASSERT(!transaction_remove_split(&t, toremove));
}

static void test_balance_currencies()
{
    Currency *USD = currency_get("USD");
    Currency *CAD = currency_get("CAD");
    AccountList al;
    accounts_init(&al, 1, USD);
    Account *a = accounts_create(&al);
    Transaction t;
    transaction_init(&t, TXN_TYPE_NORMAL, 42);

    // Let's start out with a simple one split imbalance
    Split *s = transaction_add_split(&t);
    s->account = a;
    amount_set(&s->amount, 42, USD);
    transaction_balance_currencies(&t, s);
    CU_ASSERT_EQUAL(t.splitcount, 2);
    CU_ASSERT_PTR_NULL(t.splits[1].account);
    CU_ASSERT_EQUAL(t.splits[1].amount.val, -42);
    CU_ASSERT_PTR_EQUAL(t.splits[1].amount.currency, USD);

    // What if we have no strong split? Our txn should be stable and not change
    transaction_balance_currencies(&t, NULL);
    CU_ASSERT_EQUAL(t.splitcount, 2);
    CU_ASSERT_EQUAL(t.splits[0].amount.val, 42);

    // And if we change the split to another currency?
    t.splits[1].amount.val = -22;
    t.splits[1].amount.currency = CAD;
    // The logical imbalance disappears and balancding does nothing.
    transaction_balance_currencies(&t, NULL);
    CU_ASSERT_EQUAL(t.splitcount, 2);
    CU_ASSERT_EQUAL(t.splits[0].amount.val, 42);
    CU_ASSERT_PTR_EQUAL(t.splits[0].amount.currency, USD);
    CU_ASSERT_EQUAL(t.splits[1].amount.val, -22);
    CU_ASSERT_PTR_EQUAL(t.splits[1].amount.currency, CAD);

    // But if we reverse the CAD amount? Then we have a logical imbalance and
    // we will end up with 4 splits
    t.splits[1].amount.val = 22;
    transaction_balance_currencies(&t, &t.splits[1]);
    CU_ASSERT_EQUAL(t.splitcount, 4);
    CU_ASSERT_EQUAL(t.splits[2].amount.val, -42);
    CU_ASSERT_PTR_EQUAL(t.splits[2].amount.currency, USD);
    CU_ASSERT_EQUAL(t.splits[3].amount.val, -22);
    CU_ASSERT_PTR_EQUAL(t.splits[3].amount.currency, CAD);

    accounts_deinit(&al);
}

static void test_balance()
{
    Currency *USD = currency_get("USD");
    AccountList al;
    accounts_init(&al, 2, USD);
    Account *a1 = accounts_create(&al);
    Account *a2 = accounts_create(&al);
    Transaction t;
    transaction_init(&t, TXN_TYPE_NORMAL, 42);

    // Simple imbalance to start with
    Split *s = transaction_add_split(&t);
    s->account = a1;
    amount_set(&s->amount, 42, USD);
    transaction_balance(&t, NULL, false);
    CU_ASSERT_EQUAL(t.splitcount, 2);
    CU_ASSERT_PTR_NULL(t.splits[1].account);
    CU_ASSERT_EQUAL(t.splits[1].amount.val, -42);

    // Try out keep_two_splits
    t.splits[0].amount.val = -22;
    transaction_balance(&t, &t.splits[0], true);
    // The other side follows
    CU_ASSERT_EQUAL(t.splitcount, 2);
    CU_ASSERT_EQUAL(t.splits[1].amount.val, 22);

    // But without keep_two_splits and with an account...
    t.splits[0].amount.val = 42;
    t.splits[1].account = a2;
    transaction_balance(&t, &t.splits[0], false);

    // We reverse the second split, but balance the rest with a 3rd split
    CU_ASSERT_EQUAL(t.splitcount, 3);
    CU_ASSERT_EQUAL(t.splits[1].amount.val, -22);
    CU_ASSERT_EQUAL(t.splits[2].amount.val, -20);
    CU_ASSERT_PTR_NULL(t.splits[2].account);

    accounts_deinit(&al);
}

void test_transaction_init()
{
    CU_pSuite s;

    s = CU_add_suite("Transaction", NULL, NULL);
    CU_ADD_TEST(s, test_remove_split);
    CU_ADD_TEST(s, test_balance_currencies);
    CU_ADD_TEST(s, test_balance);
}
