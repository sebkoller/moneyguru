#include <CUnit/CUnit.h>
#include <CUnit/Basic.h>
#include "../currency.h"

void test_util_init();
void test_amount_init();
void test_account_init();
void test_transaction_init();
void test_recurrence_init();

int main()
{
    currency_global_init(":memory:");
    CU_initialize_registry();
    CU_basic_set_mode(CU_BRM_VERBOSE);
    test_util_init();
    test_amount_init();
    test_account_init();
    test_transaction_init();
    test_recurrence_init();
    CU_basic_run_tests();
    CU_cleanup_registry();
    currency_global_deinit();
    return 0;
}
