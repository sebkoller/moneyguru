#include <CUnit/CUnit.h>
#include "../recurrence.h"

static time_t mkdate(int year, int month, int day)
{
    struct tm d = {0};
    d.tm_year = year - 1900;
    d.tm_mon = month - 1;
    d.tm_mday = day;
    return mktime(&d);
}

static void test_inc_daily()
{
    time_t res = inc_date(mkdate(2019, 1, 22), REPEAT_DAILY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 1, 23));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_DAILY, 42);
    CU_ASSERT_EQUAL(res, mkdate(2019, 3, 5));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_DAILY, -4);
    CU_ASSERT_EQUAL(res, mkdate(2019, 1, 18));
}

static void test_inc_weekly()
{
    time_t res = inc_date(mkdate(2019, 1, 22), REPEAT_WEEKLY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 1, 29));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_WEEKLY, -4);
    CU_ASSERT_EQUAL(res, mkdate(2018, 12, 25));
}

static void test_inc_monthly()
{
    time_t res = inc_date(mkdate(2019, 1, 22), REPEAT_MONTHLY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 2, 22));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_MONTHLY, -1);
    CU_ASSERT_EQUAL(res, mkdate(2018, 12, 22));
    res = inc_date(mkdate(2019, 1, 29), REPEAT_MONTHLY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 2, 28));
    res = inc_date(mkdate(2019, 1, 31), REPEAT_MONTHLY, 2);
    CU_ASSERT_EQUAL(res, mkdate(2019, 3, 31));
}

static void test_inc_yearly()
{
    time_t res = inc_date(mkdate(2019, 1, 22), REPEAT_YEARLY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2020, 1, 22));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_YEARLY, -1);
    CU_ASSERT_EQUAL(res, mkdate(2018, 1, 22));
    res = inc_date(mkdate(2016, 2, 29), REPEAT_YEARLY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2017, 2, 28));
    res = inc_date(mkdate(2016, 2, 29), REPEAT_YEARLY, 4);
    CU_ASSERT_EQUAL(res, mkdate(2020, 2, 29));
}

static void test_inc_weekday()
{
    // 4th tuesday
    time_t res = inc_date(mkdate(2019, 1, 22), REPEAT_WEEKDAY, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 2, 26));
    res = inc_date(mkdate(2019, 1, 22), REPEAT_WEEKDAY, -1);
    CU_ASSERT_EQUAL(res, mkdate(2018, 12, 25));
    // 5th thursday (doesn't exist in feb)
    res = inc_date(mkdate(2019, 1, 31), REPEAT_WEEKDAY, 1);
    CU_ASSERT_EQUAL(res, -1);
}

static void test_inc_weekday_last()
{
    // last tuesday
    time_t res = inc_date(mkdate(2019, 1, 29), REPEAT_WEEKDAY_LAST, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 2, 26));
    // last monday
    res = inc_date(mkdate(2019, 1, 28), REPEAT_WEEKDAY_LAST, -1);
    CU_ASSERT_EQUAL(res, mkdate(2018, 12, 31));
    // last thursday
    res = inc_date(mkdate(2019, 1, 29), REPEAT_WEEKDAY_LAST, 1);
    CU_ASSERT_EQUAL(res, mkdate(2019, 2, 26));
}

void test_recurrence_init()
{
    CU_pSuite s;

    s = CU_add_suite("Recurrence", NULL, NULL);
    CU_ADD_TEST(s, test_inc_daily);
    CU_ADD_TEST(s, test_inc_weekly);
    CU_ADD_TEST(s, test_inc_monthly);
    CU_ADD_TEST(s, test_inc_yearly);
    CU_ADD_TEST(s, test_inc_weekday);
    CU_ADD_TEST(s, test_inc_weekday_last);
}

