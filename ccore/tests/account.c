#include <CUnit/CUnit.h>
#include "../account.h"
#include "../currency.h"
#include "../util.h"

static void test_accounts_find()
{
    AccountList al;
    accounts_init(&al, NULL);

    Account *a1 = accounts_create(&al);
    account_init(a1, "fOo", NULL, ACCOUNT_ASSET);
    Account *a2 = accounts_create(&al);
    account_init(a2, " baR ", NULL, ACCOUNT_ASSET);
    Account *a3 = accounts_create(&al);
    account_init(a3, "école", NULL, ACCOUNT_ASSET);

    Account *found = accounts_find_by_name(&al, "not there");
    CU_ASSERT_PTR_NULL(found);
    found = accounts_find_by_name(&al, "foo ");
    CU_ASSERT_PTR_EQUAL(found, a1);
    found = accounts_find_by_name(&al, "BAR");
    CU_ASSERT_PTR_EQUAL(found, a2);
    // TODO: properly support locales or bring in ICU or something.
    /*found = accounts_find_by_name(&al, "ÉCOLE");*/
    /*CU_ASSERT_PTR_EQUAL(found, a3);              */
    account_deinit(a1);
    account_deinit(a2);
    account_deinit(a3);
    accounts_deinit(&al);
}

static void test_accounts_find_account_number()
{
    AccountList al;
    accounts_init(&al, NULL);

    Account *a1 = accounts_create(&al);
    account_init(a1, "foo", NULL, ACCOUNT_ASSET);
    strset(&a1->account_number, "1234");
    Account *found = accounts_find_by_name(&al, "1234");
    CU_ASSERT_PTR_EQUAL(found, a1);
    account_deinit(a1);
    accounts_deinit(&al);
}

static void test_accounts_remove()
{
    AccountList al;

    accounts_init(&al, NULL);
    Account *a1 = accounts_create(&al);
    account_init(a1, "one", NULL, ACCOUNT_ASSET);
    Account *a2 = accounts_create(&al);
    account_init(a2, "two", NULL, ACCOUNT_ASSET);
    Account *a3 = accounts_create(&al);
    account_init(a3, "three", NULL, ACCOUNT_ASSET);

    CU_ASSERT_EQUAL(al.count, 3);
    accounts_remove(&al, a2);
    CU_ASSERT_EQUAL(al.count, 2);
    CU_ASSERT_PTR_EQUAL(al.accounts[0], a1);
    CU_ASSERT_PTR_EQUAL(al.accounts[1], a3);
    accounts_deinit(&al);
}

void test_account_init()
{
    CU_pSuite s;

    s = CU_add_suite("Account", NULL, NULL);
    CU_ADD_TEST(s, test_accounts_find);
    CU_ADD_TEST(s, test_accounts_find_account_number);
    CU_ADD_TEST(s, test_accounts_remove);
}

