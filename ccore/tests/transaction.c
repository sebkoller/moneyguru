#include <CUnit/CUnit.h>
#include <assert.h>
#include "../transaction.h"

static void test_remove_split()
{
    Transaction t;
    transaction_init(&t, TXN_TYPE_NORMAL, 42);
    transaction_resize_splits(&t, 3);
    t.splits[0].amount.val = 43;
    t.splits[1].amount.val = 44;
    t.splits[2].amount.val = 45;
    Split *toremove = &t.splits[1];
    assert(transaction_remove_split(&t, toremove));
    assert(t.splitcount == 2);
    assert(t.splits[1].amount.val == 45);
    // Calling it again will remove the second split again
    assert(transaction_remove_split(&t, toremove));
    assert(t.splitcount == 1);
    assert(t.splits[0].amount.val == 43);
    // But now, the call results in trying to remove an out of bounds split and
    // fails.
    assert(!transaction_remove_split(&t, toremove));
}

void test_transaction_init()
{
    CU_pSuite s;

    s = CU_add_suite("Transaction", NULL, NULL);
    CU_ADD_TEST(s, test_remove_split);
}
