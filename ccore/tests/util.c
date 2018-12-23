#include <CUnit/CUnit.h>
#include <stdlib.h>
#include "../util.h"

static void test_strstrip()
{
    char *dst;

    CU_ASSERT_FALSE(strstrip(&dst, ""));
    CU_ASSERT_FALSE(strstrip(&dst, "foo"));
    CU_ASSERT_TRUE_FATAL(strstrip(&dst, " foo "));
    CU_ASSERT_STRING_EQUAL(dst, "foo");
    free(dst);
    CU_ASSERT_TRUE_FATAL(strstrip(&dst, "  "));
    CU_ASSERT_STRING_EQUAL(dst, "");
    free(dst);
}

void test_util_init()
{
    CU_pSuite s;

    s = CU_add_suite("Util", NULL, NULL);
    CU_ADD_TEST(s, test_strstrip);
}


