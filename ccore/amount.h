#pragma once
#include <stdint.h>
#include <stdbool.h>

#include "currency.h"

typedef struct {
    int64_t val;
    Currency *currency;
} Amount;

Amount*
amount_init(int64_t val, Currency *currency);

void
amount_free(Amount *amount);

Amount*
amount_zero();

bool
amount_check(Amount *first, Amount *second);

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

/* Parse number in `s` and sets its numerical value in `dest`.
 *
 * The returned value is a "floated integer", an integer that represents a
 * float, `exponent` being the digit where the decimal separator is. Example:
 * 1234 w/ exp 3 -> 1.234
 *
 * This function deals with grouping separators and spurious stuff that might
 * be around numbers (dollar signs etc.). Grouping seps can be any non-zero
 * char, but it has to stay the same all the way. Otherwise it's an error. If
 * the last non-digit character before the last chunk of digits is a "." or a
 * ",", then that's the decimal sep.
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
    int64_t *dest, const char *s, uint8_t exponent, bool auto_decimal_place);
