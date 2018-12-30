#include <CUnit/CUnit.h>
#include <locale.h>
#include "../accounts.h"
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
    // "école" under a C locale will not work properly. However, this value is
    // there to make sure that all hell doesn't break lose either when adding
    // this broken value.
    account_init(a3, "école", NULL, ACCOUNT_ASSET);

    Account *found = accounts_find_by_name(&al, "not there");
    CU_ASSERT_PTR_NULL(found);
    found = accounts_find_by_name(&al, "foo ");
    CU_ASSERT_PTR_EQUAL(found, a1);
    found = accounts_find_by_name(&al, "BAR");
    CU_ASSERT_PTR_EQUAL(found, a2);
    accounts_deinit(&al);
}

static void test_accounts_find_locale()
{
    char *locales[] = {"fr_CA.UTF-8", "fr_FR.UTF-8", NULL};
    char *loc = NULL;
    int lindex = 0;
    while (loc == NULL && locales[lindex] != NULL) {
        loc = setlocale(LC_ALL, locales[lindex]);
        lindex++;
    }

    if (loc == NULL) {
        printf("Can't run the test_accounts_find_locale() test: no fr locale. Skipping\n");
        return;
    }
    printf("Running test with %s\n", loc);
    AccountList al;
    accounts_init(&al, NULL);

    Account *a1 = accounts_create(&al);
    account_init(a1, "fOo", NULL, ACCOUNT_ASSET);
    Account *a2 = accounts_create(&al);
    account_init(a2, "école", NULL, ACCOUNT_ASSET);
    Account *found = accounts_find_by_name(&al, "ÉCOLE");
    CU_ASSERT_PTR_EQUAL(found, a2);
    accounts_deinit(&al);
    setlocale(LC_ALL, "C");
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

static void test_accounts_rename()
{
    AccountList al;

    accounts_init(&al, NULL);
    Account *a1 = accounts_create(&al);
    account_init(a1, "one", NULL, ACCOUNT_ASSET);
    CU_ASSERT_TRUE_FATAL(accounts_rename(&al, a1, "renamed"));
    CU_ASSERT_PTR_EQUAL(accounts_find_by_name(&al, "renamed"), a1);
    CU_ASSERT_PTR_NULL(accounts_find_by_name(&al, "one"));
    Account *a2 = accounts_create(&al);
    account_init(a2, "two", NULL, ACCOUNT_ASSET);
    // name clash, abort
    CU_ASSERT_FALSE_FATAL(accounts_rename(&al, a2, "renamed"));
    CU_ASSERT_PTR_EQUAL(accounts_find_by_name(&al, "renamed"), a1);
    CU_ASSERT_PTR_EQUAL(accounts_find_by_name(&al, "two"), a2);

    // We *can*, however, rename the same account with an "almost-same" name
    CU_ASSERT_TRUE_FATAL(accounts_rename(&al, a1, "RENAMED"));
    CU_ASSERT_PTR_EQUAL(accounts_find_by_name(&al, "renamed"), a1);
    CU_ASSERT_PTR_EQUAL(accounts_find_by_name(&al, "RENAMED"), a1);

    accounts_deinit(&al);
}


void test_account_init()
{
    CU_pSuite s;

    s = CU_add_suite("Account", NULL, NULL);
    CU_ADD_TEST(s, test_accounts_find);
    CU_ADD_TEST(s, test_accounts_find_locale);
    CU_ADD_TEST(s, test_accounts_find_account_number);
    CU_ADD_TEST(s, test_accounts_remove);
    CU_ADD_TEST(s, test_accounts_rename);
}

