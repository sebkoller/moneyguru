#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <math.h>
#include <ctype.h>

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

bool
amount_parse_single(
    int64_t *dest, const char *s, uint8_t exponent, bool auto_decimal_place)
{
    int i = 0;
    // index of the first digit
    int istart;
    // index of the last digit
    int iend;
    int64_t val = 0;
    int last_digit_group_count = 0;
    char c;
    char last_sep;
    // first sep we encounter becomes the grouping sep. we then enforce
    // homogenity.
    char grouping_sep = '\0';
    bool last_sep_breaks_grouping = false;
    bool is_negative = false;

    // 1. First pass
    while (s[i] != '\0') {
        if (isdigit(s[i])) {
            istart = i;
            break;
        } else if (s[i] == '-') {
            is_negative = true;
        }
        i++;
    }
    while (s[i] != '\0') {
        if (isdigit(s[i])) {
            if (i > 0 && !isdigit(s[i-1])) {
                last_digit_group_count = 0;
            }
            iend = i;
            last_digit_group_count++;
        }
        i++;
    }
    if (s[istart] == '\0') {
        // no digit
        return false;
    }
    if (istart > 0 && s[istart-1] == '.' || s[istart-1] == ',') {
        // number starts with a . or ,. Do as if there was a "0" in front.
        istart--;
    }

    // 2. Second pass
    for (i=istart; i<=iend; i++) {
        c = s[i];
        if ((uint8_t)c == 0xc2) {
            // special case: 0xc2. Our string comes from python
            // utf8-encoded. This generally doesn't bother us, we still
            // have one-byte characters. There's only the '\xa0' grouping
            // sep that we want to support, and when it's encoded as utf-8,
            // it's 0xc2a0. So, whenever we see 0xc2, we ignore it and
            // process the next char.
            i++;
            continue;
        } else if ((uint8_t)c == 0xa0) {
            // See 0xc2: non-breakable space. treat it as a space.
            c = ' ';
        }
        if (isdigit(c)) {
            val = (val * 10) + (c - '0');
        } else {
            if (i > istart && !isdigit(s[i-1])) {
                // We had a streak of more than one non-digit. It's accepted
                // before or after all digits, but not in between. Error.
                return false;
            }
            if (last_sep_breaks_grouping) {
                // We now have 2 separators that aren't the grouping sep. The
                // first one could have been the decimal sep, but now it's
                // impossible. Error.
                return false;
            }
            if (grouping_sep == '\0') {
                grouping_sep = c;
            } else if (c != grouping_sep) {
                if (c == '.' || c == ',') {
                    // `c` breaks the grouping seps, but it might be our
                    // decimal sep. Let's give it a chance. But if we encounter
                    // another sep, it's game over
                    last_sep_breaks_grouping = true;
                } else {
                    // error, heterogenous grouping seps.
                    return false;
                }
            }
            last_sep = c;
        }
    }

    // 3. Wrapping up and returning

    // Wrapped in parens?
    if (istart > 0 && s[istart-1] == '(' && s[iend+1] == ')') {
        is_negative = true;
    }

    if (is_negative) {
        val *= -1;
    }

    if (last_sep == '.' || last_sep == ',') {
        // We have a decimal separator
        //
        // Special case: digit count is exactly 3, more than exponent, and
        // grouping_sep is a possible digital sep. We consider this a grouping
        // sep. Example: 1,000 USD -> 1000.00
        if (last_digit_group_count == 3 && last_digit_group_count > exponent
                && (grouping_sep == '.' || grouping_sep == ',')) {
            *dest = val * pow(10, exponent);
            return true;
        }
        // It's possible that out digit count is not the same as our currency
        // exponent. Let's adjust.
        if (last_digit_group_count > exponent) {
            // too many digits. trim.
            val /= pow(10, last_digit_group_count - exponent);
        } else if (last_digit_group_count < exponent) {
            // not enough digits, fill right-side zeroes.
            val *= pow(10, exponent - last_digit_group_count);
        }
    } else {
        if (!auto_decimal_place) {
            // if auto_decimal_place is on, we already have our final value.
            // otherwise, we have to shift left.
            val *= pow(10, exponent);
        }
    }
    *dest = val;
    return true;
}
