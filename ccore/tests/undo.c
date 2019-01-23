#include <CUnit/CUnit.h>
#include "../accounts.h"
#include "../undo.h"

static void test_string_ownership()
{
    /* Verify that string ownership is handled properly */
    AccountList al = {0};
    Currency *CAD = currency_get("CAD");
    accounts_init(&al, CAD);
    Account *a = accounts_create(&al);
    account_init(a, "foo", CAD, ACCOUNT_ASSET);
    UndoStep us = {0};
    Account *changed_accounts[2] = {a, NULL};
    undostep_init(&us, NULL, NULL, changed_accounts);
    // We now have a copy of `a` in `us`. Now, let's change the name so that
    // we free the string "foo".
    account_name_set(a, "bar");
    // The "foo" we had is supposed to properly be kept in memory. To verify
    // this, let's perform an undo and check for the account name.
    undostep_undo(&us, &al);
    CU_ASSERT_STRING_EQUAL(a->name, "foo"); // no segfault
    undostep_redo(&us, &al);
    CU_ASSERT_STRING_EQUAL(a->name, "bar"); // no segfault
    undostep_undo(&us, &al);
    CU_ASSERT_STRING_EQUAL(a->name, "foo"); // no segfault
}

void test_undo_init()
{
    CU_pSuite s;

    s = CU_add_suite("Undo", NULL, NULL);
    CU_ADD_TEST(s, test_string_ownership);
}

