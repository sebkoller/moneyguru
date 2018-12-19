#include <CUnit/CUnit.h>
#include <CUnit/Basic.h>

void test_transaction_init();

int main()
{
    CU_initialize_registry();
    test_transaction_init();
    CU_basic_run_tests();
    CU_cleanup_registry();
    return 0;
}
