#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>

#include "amount.h"

static Amount *g_zero = NULL;

/* Private */

static int
group_intfmt(char *dest, uint64_t val, char grouping_sep) {
    int64_t left;
    int written = 0;
    int rc;

    if (val >= 1000) {
        left = val / 1000;
        rc = group_intfmt(dest, left, grouping_sep);
        if (rc < 0) {
            return rc;
        }
        dest[rc] = grouping_sep;
        written += rc + 1;
        dest = &(dest[written]);
        val -= (left * 1000);
    }
    rc = sprintf(dest, "%ld", val);
    if (rc < 0) {
        return rc;
    } else {
        written += rc;
        return written;
    }
}

/* Public */
Amount*
amount_init(int64_t val, Currency *currency)
{
    Amount *res;

    res = malloc(sizeof(Amount));
    if (res == NULL) {
        return NULL;
    }
    res->val = val;
    res->currency = currency;
    return res;
}

void
amount_free(Amount *amount)
{
    if (amount != NULL) {
        free(amount);
    }
}

Amount*
amount_zero()
{
    if (g_zero == NULL) {
        g_zero = amount_init(0, NULL);
    }
    return g_zero;
}

bool
amount_check(Amount *first, Amount *second)
{
    if (!(first && second)) {
        // A NULL amount? not cool.
        return false;
    }
    if (first->val && second->val) {
        return first->currency == second->currency;
    } else {
        // One of them is zero. compatible.
        return true;
    }
}

bool
amount_format(
    char *dest,
    Amount *amount,
    bool with_currency,
    bool blank_zero,
    char decimal_sep,
    char grouping_sep)
{
    int64_t val, left, right;
    int rc, seppos;
    unsigned int exp;
    char buf[64];

    if (amount == NULL) {
        dest[0] = '\0';
        return true;
    }

    val = amount->val;
    if (!val) {
        if (blank_zero) {
            dest[0] = '\0';
            return true;
        } else if (amount->currency == NULL) {
            strcpy(dest, "0.00");
            return true;
        }
        // If zero, but with a currency, we're in a "zero_currency" situation.
        // continue normally.
    }

    if (amount->currency == NULL) {
        // nonzero and null currency? something's wrong.
        return false;
    }
    exp = amount->currency->exponent;
    if (exp > CURRENCY_MAX_EXPONENT) {
        // Doesn't make much sense
        return false;
    }

    if (with_currency) {
        rc = snprintf(
            dest, CURRENCY_CODE_MAXLEN + 1, "%s ", amount->currency->code);
        if (rc < 0) {
            return false;
        }
        dest = &(dest[rc]);
    }

    if (val < 0) {
        dest[0] = '-';
        dest = &(dest[1]);
        val *= -1;
    }

    left = val / pow(10, exp);
    right = val - (left * pow(10, exp));
    if (grouping_sep != 0) {
        rc = group_intfmt(dest, left, grouping_sep);
    } else {
        rc = sprintf(dest, "%ld", left);
    }
    if (rc < 0) {
        return false;
    }
    // little tick to ensure dynamic padding of right part: let's overshoot by
    // one, with the leftmost digit being written where the digit set will be.
    seppos = rc; // remember where we were: decimal_sep is going there.
    right += pow(10, exp);
    rc = sprintf(&(dest[rc]), "%ld", right);
    if (rc < 0) {
        return false;
    }
    dest[seppos] = decimal_sep;
    dest[seppos + rc] = '\0';
    return true;
}

