#include <CUnit/CUnit.h>
#include <CUnit/Basic.h>
#include "../currency.h"

void test_transaction_init();

int main()
{
    currency_global_init(":memory:");
    CU_initialize_registry();
    test_transaction_init();
    CU_basic_run_tests();
    CU_cleanup_registry();
    currency_global_deinit();
    return 0;
}
