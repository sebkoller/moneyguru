#pragma once
#include <stdint.h>
#include <stdbool.h>

#include "currency.h"

typedef struct {
    int64_t val;
    Currency *currency;
} Amount;

void
amount_copy(Amount *dest, const Amount *src);

// copy src int dest but negate the value.
void
amount_neg(Amount *dest, const Amount *src);

void
amount_set(Amount *dest, int64_t val, Currency *currency);

const Amount*
amount_zero(void);

int64_t
amount_slide(int64_t val, uint8_t fromexp, uint8_t toexp);

bool
amount_check(const Amount *first, const Amount *second);

bool
amount_same_side(const Amount *a, const Amount *b);

/* Returns a formatted string from `amount`.

From a regular amount, will return (depending on the options of course),
something like "CAD 42.54", or maybe only "42.54".

This all depends on `default_currency`, which is a settings in moneyGuru which
we pass onto this function. To lighten the UI a bit, moneyGuru only displays
"foreign" (non-default) currencies in amounts. Therefore, if `amount.currency`
is the same as `default_currency`, we don't include our amount currency code in
our result.

When amount is null (zero), we don't display currency code because, well,
nothingness doesn't have a currency.

Another caveat: The number of digits we print depends on our currency's
`exponent` (most of the time 2, but sometimes 0 or 3).

Arguments:

dest: destination string.
amount: the amount to format.
with_currency: prepend amount's currency code to it.
blank_zero: if true, a 0 amount prints as '' instead of '0.00'
decimal_sep: the character to use as a decimal separator.
grouping_sep: the character to use as a grouping separator. set to 0 to disable
              grouping.
*/

bool
amount_format(
    char *dest,
    Amount *amount,
    bool with_currency,
    bool blank_zero,
    char decimal_sep,
    char grouping_sep);

/* Parse number in `s` and return its grouping separator
 *
 * Returns '\0' if it has no grouping separator or if the number is invalid.
 *
 * A grouping separator is a non-digit character that is in-between digits and
 * stays consisten across the number. The only other non-digit char that can
 * get in between digits without making it invalid is the decimal separator and
 * it has to be last.
 */
char
amount_parse_grouping_sep(const char *s);

/* Parse `s` and look for a currency code
 *
 * If it has one, returns the corresponding Currency. Otherwise, returns NULL.
 */
Currency *
amount_parse_currency(
    const char *s, const char *default_currency, bool strict_currency);

/* Parse number in `s` and sets its numerical value in `dest`.
 *
 * The returned value is a "floated integer", an integer that represents a
 * float, `exponent` being the digit where the decimal separator is. Example:
 * 1234 w/ exp 3 -> 1.234
 *
 * If grouping_sep is not '\0', we properly ignore them. Otherwise, we only
 * accept a single decimal separator in between numbers. Anything else makes
 * the number invalid.
 *
 * This function deals with spurious stuff that might be around numbers (dollar
 * signs etc.).  If the last non-digit character before the last chunk of
 * digits is a "." or a ",", then that's the decimal sep.
 *
 * If auto_decimal_place is true and there's no decimal sep, then the amount is
 * going to be divided by 10 ** exponent. Typing a literal "1000" with exp 2
 * will yield 10.00.
 *
 * Having more than one character in between chunks of numbers (around, it's
 * ok) is an error.
 *
 * "-" in the number's prefix makes it negative. Parens too. $-10, -$10, $(10)
 * are negative.
 *
 * Returns true on success, false on error.
 */
bool
amount_parse_single(
    int64_t *dest, const char *s, uint8_t exponent, bool auto_decimal_place,
    char grouping_sep);

/* Parse simple math expressions involving amounts.
 *
 * Parse and resolve stuff like "1+2*3" into 7 and also support the
 * peculiarities of amount matching. Like `amount_parse_single()`, will return
 * a "floated integer" that has the exponent `exponent`.
 *
 * Other than parsing expressions, it behaves similarly to
 * `amount_parse_single()` (in fact, it calls it). Theres one little caveat:
 *
 * FIRST OPERAND RULE: There's an ambiguity with the '.' character. In an
 * amount, it can be a thousands separator, but also as a decimal separator.
 * We already have a disambiguation rule in `amount_parse_single()`, but we
 * must go a step further here because we could want to multiply an amount by a
 * decimal number that has a precision greater than `exponent`. Our solution is
 * to only consider the first operand as an amount. The other operands are
 * considered as "decimals", which means that they can't possibly have a
 * thousands separator.
 */
bool
amount_parse_expr(
    int64_t *dest,
    const char *s,
    uint8_t exponent);

/* Returns an Amount from `s` and writes it in `dest`.
 *
 * We can parse strings like "42.54 cad" or "CAD 42.54".
 *
 * If `default_currency` is set, we can parse amounts that don't contain a
 * currency code and will give the amount that currency.
 *
 * If `with_expression` is true, we can parse stuff like "42*4 cad" or "usd
 * (1+2)/3". If you know your string doesn't contain any expression, turn this
 * flag off to greatly speed up parsing.
 *
 * `auto_decimal_place` allows for quick decimal-less typing. We assume that
 * the number has been typed to the last precision digit and automatically
 * place our decimal separator if there isn't one. For example, "1234" would be
 * parsed as "12.34" in a CAD context (in BHD, a currency with 3 digits, it
 * would be parsed as "1.234"). This doesn't work with expressions.
 */

bool
amount_parse(
    Amount *dest,
    const char *s,
    const char *default_currency,
    bool with_expression,
    bool auto_decimal_place,
    bool strict_currency);

/* Convert src's value into dest using rate at specified date.
 *
 * We expect dest to already have a currency set.
 */
bool
amount_convert(Amount *dest, const Amount *src, time_t date);
