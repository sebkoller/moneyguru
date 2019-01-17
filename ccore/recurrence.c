#include "recurrence.h"

/* Private */
static time_t
_inc_daily(time_t date, int count)
{
    return date + (SECS_IN_DAY * count);
}

static time_t
_inc_weekly(time_t date, int count)
{
    return _inc_daily(date, count * 7);
}

static time_t
_inc_monthly(time_t date, int count)
{
    struct tm *d = gmtime(&date);
    if (d == NULL) {
        return -1;
    }
    d->tm_mon += count;
    int day_before = d->tm_mday;
    time_t res = mktime(d);
    if (day_before != d->tm_mday) {
        // mktime() normalized our tm struct, which means that we had an
        // out of bound day (31st or 29+ in Feb). What we want now is the last
        // day of the previous month.
        d->tm_mday = 0; // "1 - 1", normalized by glibc
        res = mktime(d);
    }
    return res;
}

static time_t
_inc_yearly(time_t date, int count)
{
    return _inc_monthly(date, count * 12);
}

static time_t
_inc_weekday(time_t date, int count)
{
    struct tm *d = gmtime(&date);
    if (d == NULL) {
        return -1;
    }
    int wday = d->tm_wday;
    int wno = (d->tm_mday - 1) / 7;
    // now that we have our target wday and wno, go in "first day of the month"
    // mode so that we can calculate the difference from there.
    d->tm_mday = 1;
    d->tm_mon += count;
    mktime(d);
    int diff = wday - d->tm_wday;
    if (diff < 0) {
        diff += 7;
    }
    d->tm_mday = wno * 7 + diff + 1;
    int month_before = d->tm_mon;
    time_t res = mktime(d);
    if (d->tm_mon != month_before) {
        // tm_day went out of bounds. The day we're trying to get doesn't
        // exist for the given month. Error.
        return -1;
    } else {
        return res;
    }

}

static time_t
_inc_weekday_last(time_t date, int count)
{
    struct tm *d = gmtime(&date);
    if (d == NULL) {
        return -1;
    }
    int wday = d->tm_wday;
    // day 0 is out of bounds, but because we do "count + 1" below, that will
    // give us the last day of our target month.
    d->tm_mday = 0;
    d->tm_mon += count + 1;
    mktime(d);
    int diff = d->tm_wday - wday;
    if (diff < 0) {
        diff += 7;
    }
    d->tm_mday -= diff;
    return mktime(d);
}

/* Public */
time_t
inc_date(time_t date, RepeatType repeat_type, int count)
{
    switch (repeat_type) {
        case REPEAT_DAILY: return _inc_daily(date, count);
        case REPEAT_WEEKLY: return _inc_weekly(date, count);
        case REPEAT_MONTHLY: return _inc_monthly(date, count);
        case REPEAT_YEARLY: return _inc_yearly(date, count);
        case REPEAT_WEEKDAY: return _inc_weekday(date, count);
        case REPEAT_WEEKDAY_LAST: return _inc_weekday_last(date, count);
        default: return date;
    }
}
