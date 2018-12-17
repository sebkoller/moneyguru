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
    bool leftmost;

    if (val >= 1000) {
        leftmost = false;
        left = val / 1000;
        rc = group_intfmt(dest, left, grouping_sep);
        if (rc < 0) {
            return rc;
        }
        dest[rc] = grouping_sep;
        written += rc + 1;
        dest = &(dest[written]);
        val -= (left * 1000);
    } else {
        leftmost = true;
    }
    rc = sprintf(dest, leftmost ? "%ld" : "%03ld", val);
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

void
amount_copy(Amount *dest, const Amount *src)
{
    dest->val = src->val;
    dest->currency = src->currency;
}

Amount*
amount_zero(void)
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

int64_t
amount_slide(int64_t val, uint8_t fromexp, uint8_t toexp)
{
    if (toexp == fromexp) {
        return val;
    } else if (toexp > fromexp) {
        return val * pow(10, toexp - fromexp);
    } else {
        return val / pow(10, fromexp - toexp);
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

char
amount_parse_grouping_sep(const char *s)
{
    int i = 0;
    char res = '\0';
    // We got an invalid char, but it's ok as long as there's no other digit
    // after it.
    bool invalid_if_other_digit = false;
    // We encountered a decimal sep. it's fine, as long as it's the last.
    bool had_decimal_sep = false;
    // We have a result, but we need to encounter another digit before
    // confirming it.
    bool needs_a_digit = false;

    // ignore everything before first digit
    while (s[i] != '\0' && !isdigit(s[i])) i++;
    while (s[i] != '\0') {
        char c = s[i];
        if ((unsigned char)c == 0xa0) {
            // We consider 0xa0 and ' ' to be the same
            c = ' ';
        }
        if (!isdigit(c)) {
            if (res == '\0') {
                // first encounter, that's possibly our result, if we encounter
                // another digit.
                res = c;
                needs_a_digit = true;
            } else if (had_decimal_sep) {
                invalid_if_other_digit = true;
            } else if (c == res) {
                // grouping sep, everything normal
            } else if (c == '.' || c == ',') {
                had_decimal_sep = true;
            } else {
                // Some spurious stuff
                invalid_if_other_digit = true;
            }
        } else if (invalid_if_other_digit) {
            return '\0';
        } else {
            needs_a_digit = false;
        }
        i++;
    }
    if (needs_a_digit) {
        // our result wasn't followed by a digit, so it's just a random suffix
        // char. we have no grouping sep.
        return '\0';
    } else {
        return res;
    }
}

Currency *
amount_parse_currency(
    const char *s, const char *default_currency, bool strict_currency)
{
    int i = 0;
    int len = 0;
    char buf[4] = {0};
    Currency *currency = NULL;

    while (true) {
        char c = s[i];
        if (isalpha(c)) {
            len++;
        } else {
            if (len == 3) {
                // We have 3 chars. Let's see if it's a currency.
                buf[0] = toupper(s[i-3]);
                buf[1] = toupper(s[i-2]);
                buf[2] = toupper(s[i-1]);
                currency = currency_get(buf);
                if (currency != NULL) {
                    return currency;
                } else if (strict_currency) {
                    return NULL;
                }
            }
            len = 0;
        }
        if (s[i] == '\0') {
            if (default_currency != NULL) {
                return currency_get(default_currency);
            } else {
                return NULL;
            }
        }
        i++;
    }
}

bool
amount_parse_single(
    int64_t *dest, const char *s, uint8_t exponent, bool auto_decimal_place,
    char grouping_sep)
{
    int i = 0;
    // index of the first digit
    int istart = -1;
    // index of the last digit
    int iend = -1;
    int64_t val = 0;
    int last_digit_group_count = 0;
    char last_sep = '\0';
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
    if (istart < 0) {
        // no digit
        return false;
    }
    if ((istart > 0 && s[istart-1] == '.') || s[istart-1] == ',') {
        // number starts with a . or ,. Do as if there was a "0" in front.
        istart--;
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

    // 2. Second pass
    for (i=istart; i<=iend; i++) {
        char c = s[i];
        if ((unsigned char)c == 0xa0) {
            // We consider 0xa0 and ' ' to be the same
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
            } else if (c != grouping_sep) {
                if (c == '.' || c == ',') {
                    // `c` breaks the grouping seps, but it might be our
                    // decimal sep. Let's give it a chance. But if we encounter
                    // another sep, it's game over
                    last_sep_breaks_grouping = true;
                } else {
                    // invalid character, error.
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

/* Expression parsing */
/* Inspired by https://stackoverflow.com/a/9329509, with a personal twist...*/

struct ExprParse {
    const char *s;
    // The exponent used to parse "amount" numbers
    uint8_t amount_exponent;
    // The exponent we use to parse decimal numbers. a constant set high to
    // allow for better accuracy. We normalize amounts to this exponent after
    // parsing so that we can apply operators on comparable numbers.
    uint8_t exponent;
    /* FIRST OPERAND RULE: There's an ambiguity with the '.' character. In an
     * amount, it can be a thousands separator. Our solution is to only consider
     * the first  operand as an amount. The other operands are considered as
     * "decimals", which means that they can't possibly have a thousands
     * separator. */
    bool had_amount;
    bool error;
};

static int64_t
expr_addsubst(struct ExprParse *p);

static int64_t
expr_amount(struct ExprParse *p)
{
    static const char delimiters[] = "+-*/)";
    static const char invalid[] = "(";
    char buf[64];
    int i = 0;
    int64_t val;
    // We have a special situation with '-': it's a delimiter for a binary
    // digits, but also a unary operator on the digit. As long as we didn't see
    // any digit yet, we ignore the '-'
    bool had_digit = false;
    char grouping_sep = '\0';
    uint8_t exponent = p->exponent;

    while (true) {
        if (i == 64) {
            // something's wrong
            p->error = true;
            return 0;
        }
        char c = p->s[i];
        if (!had_digit && c == '-') {
            // '-' is a unary operator. do nothing.
        }
        // delimiter's terminating \0 is part of the searched chars
        else if (strchr(delimiters, c) != NULL) {
            // We've reached the end, we have our buffer
            buf[i] = '\0';
            p->s += i;
            if (!p->had_amount) {
                grouping_sep = amount_parse_grouping_sep(buf);
                exponent = p->amount_exponent;
            }
            if (amount_parse_single(&val, buf, exponent, false, grouping_sep)) {
                if (exponent != p->exponent) {
                    // we have to normalize our amount
                    val *= pow(10, p->exponent - exponent);
                }
                p->had_amount = true;
                return val;
            } else {
                p->error = true;
                return 0;
            }
        } else if (strchr(invalid, c)) {
            p->error = true;
            return 0;
        }
        if isdigit(c) {
            had_digit = true;
        }
        buf[i] = c;
        i++;
    }
}

static int64_t
expr_parens(struct ExprParse *p)
{
    int64_t val = 0;
    // Let's skip whitespace
    while (p->s[0] != '\0' && p->s[0] == ' ') {
        p->s++;
    }
    if (p->s[0] == '(') {
        p->s++;
        val = expr_addsubst(p);
        if (p->error || p->s[0] != ')') {
            p->error = true;
            return 0;
        }
        p->s++;
        return val;
    } else {
        return expr_amount(p);
    }
}

static int64_t
expr_multdiv(struct ExprParse *p)
{
    int64_t tmp;
    int64_t val = expr_parens(p);
    while (!p->error && (p->s[0] == '*' || p->s[0] == '/')) {
        char c = *(p->s++);
        if (c == '*') {
            val *= expr_parens(p);
            val /= pow(10, p->exponent);
        }
        else {
            tmp = expr_parens(p);
            if (tmp == 0) {
                p->error = true;
                return 0;
            }
            val *= pow(10, p->exponent);
            val /= tmp;
        }
    }
    return val;
}

static int64_t
expr_addsubst(struct ExprParse *p)
{
    int64_t val = expr_multdiv(p);
    while (!p->error && (p->s[0] == '+' || p->s[0] == '-')) {
        char c = *(p->s++);
        if (c == '+') {
            val += expr_multdiv(p);
        } else {
            val -= expr_multdiv(p);
        }
    }
    return val;
}

bool
amount_parse_expr(
    int64_t *dest, const char *s, uint8_t exponent)
{
    struct ExprParse p;
    int64_t val;

    p.s = s;
    p.amount_exponent = exponent;
    p.exponent = 5;
    p.had_amount = false;
    p.error = false;
    val = expr_addsubst(&p);
    // `val` is in p.exponent. normalize it to requested exponent
    val /= pow(10, p.exponent - exponent);
    if (!p.error) {
        *dest = val;
        return true;
    } else {
        return false;
    }
}

bool
amount_convert(Amount *dest, Amount *src, time_t date)
{
    double rate;

    if (!src->val) {
        dest->val = 0;
        return true;
    }
    if (currency_getrate(date, src->currency, dest->currency, &rate) != CURRENCY_OK) {
        return false;
    }
    dest->val = amount_slide(
        src->val * rate,
        src->currency->exponent,
        dest->currency->exponent);
    return true;
}
