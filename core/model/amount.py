# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import re
from itertools import groupby

from .currency import Currencies
from ._ccore import Amount


class UnsupportedCurrencyError(ValueError):
    """We're trying to parse an amount specifying an unsupported currency."""
    def __init__(self, currency):
        self.currency = currency
        ValueError.__init__(self, "Unsupported currency: {}".format(currency))

re_arithmetic_operators = re.compile(r"[+\-*/()]")
re_not_arithmetic_operators = re.compile(r"[^+\-*/()]+")
# 3 letters (capturing)
re_currency = re.compile(r'([a-zA-Z]{3}\s*$)|(^\s*[a-zA-Z]{3})')
# grouping separator. A thousand sep character that has digit before and after *if* the right part
# has 3 digits. \xa0 is a non-breaking space. We sometimes end up with those in space-separated
# environments.
re_grouping_sep = re.compile(r"(?<=\d)[.\s\xA0,'](?=\d{3})")
# A dot or comma followed by digits followed by the end of the string.
# currencies with 2 decimal places
re_decimal_sep_2 = re.compile(r"[,.](?=\d{1,2}$)")
# currencies with 3 or more decimal places
re_decimal_sep_x = re.compile(r"[,.](?=\d{1,10}$)")
# A valid amount, once it has been pre-processed
re_amount = re.compile(r"\d+\.\d+|\.\d+|\d+")

def format_amount(
        amount, default_currency=None, blank_zero=False, zero_currency=None, decimal_sep='.',
        grouping_sep=''):
    """Returns a formatted string from ``amount``.

    From a regular amount, will return (depending on the options of course), something like
    "CAD 42.54", or maybe only "42.54".

    This all depends on ``default_currency``, which is a settings in moneyGuru which we pass onto
    this function. To lighten the UI a bit, moneyGuru only displays "foreign" (non-default)
    currencies in amounts. Therefore, if ``amount.currency`` is the same as ``default_currency``, we
    don't include our amount currency code in our result.

    When amount is null (zero), we don't display currency code because, well, nothingness doesn't
    have a currency.

    Another caveat: The number of digits we print depends on our currency's
    :attr:`exponent <.Currency.exponent>` (most of the time 2, but sometimes 0 or 3).

    :param default_currency: The user's "native" currency.
    :type default_currency: :class:`.Currency`.
    :param bool blank_zero: If amount is zero, return ``''`` instead of ``0.00``.
    :param zero_currency: If we really want to specify a currency when amount is zero, we can
                          specify which here.
    :type zero_currency: :class:`.Currency`.
    :param str decimal_sep: The decimal separator to use for formatting.
    :param str grouping_sep: The thousands separator to use for formatting.

    .. seealso:: :doc:`/currencies`
    """
    if amount is None:
        return ''
    number = '0.00'
    currency = None
    negative = False
    if not amount:
        if blank_zero:
            return ''
        elif zero_currency is not None and zero_currency != default_currency:
            currency = zero_currency.code
    else:
        negative = amount < 0
        number = '%.*f' % (amount.currency.exponent, float(abs(amount)))
        if amount.currency != default_currency:
            currency = amount.currency.code
    if decimal_sep != '.':
        number = number.replace('.', decimal_sep)
    if grouping_sep:
        # Yup, this code is complicated, but grouping digits *is* complicated.
        splitted = number.split(decimal_sep)
        left = splitted[0]
        groups = []
        for _, pair_group in groupby(enumerate(reversed(left)), lambda pair: pair[0] // 3):
            groups.append(''.join(reversed([pair[1] for pair in pair_group])))
        splitted[0] = grouping_sep.join(reversed(groups))
        number = decimal_sep.join(splitted)
    if negative:
        number = '-' + number
    if currency is not None:
        number = '%s %s' % (currency, number)
    return number

def parse_amount_expression(string, exponent):
    # Parse an expression. Before we can do that, we need to replace all amounts with their parsed
    # and then reformatted counterparts.
    # FIRST OPERAND RULE: There's an ambiguity with the '.' character. In an amount, it can be a
    # thousands separator. See #379 for details, but our solution is to only consider the first
    # operand as an amount. The other operands are considered as "decimals", which means that they
    # can't possibly have a thousands separator.
    def repl(match):
        s = match.group(0).strip()
        if not s:
            return None
        nonlocal hadfirstmatch
        if hadfirstmatch:
            repl_exponent = 10 # meaning: many decimals
        else:
            repl_exponent = exponent
            hadfirstmatch = True
        parsed = parse_amount_single(s, repl_exponent, auto_decimal_place=False, parens_for_negatives=False)
        fmt = '{{:1.{}f}}'.format(repl_exponent)
        return fmt.format(parsed)

    hadfirstmatch = False
    result = re_not_arithmetic_operators.sub(repl, string)
    return result

def parse_amount_single(string, exponent, auto_decimal_place, parens_for_negatives=True):
    # Parse a string which contains a single amount (not an expression) and return a float
    # Now, we have a string that might have thousand separators and might or might not have
    # a decimal separator, which might be either "," or ".". We'll first find our decimal sep
    # and replace it with a placeholder char, find all thousand seps, replace them with nothing.
    if exponent >= 3:
        string = re_decimal_sep_x.sub('|', string)
    elif exponent == 2:
        string = re_decimal_sep_2.sub('|', string)
    else:
        pass # No decimal sep
    string = re_grouping_sep.sub('', string)
    string = string.replace('|', '.')
    if auto_decimal_place and string.isdigit():
        if exponent:
            string = string.rjust(exponent, '0')
            string = string[:-exponent] + '.' + string[-exponent:]
    try:
        value = float(string)
    except ValueError:
        # There might be some crap around the amount. Remove it and try again.
        m = re_amount.search(string)
        if m is None:
            raise ValueError("'{}' is not an amount".format(string))
        value = float(string[m.start():m.end()])
        # Handle negative amounts either starting with a minus sign or surrounded
        # by parenthasis, which is used frequently to denote a negative in finance.
        # e.g. -12.30 == (12.30), if we're allowing parens to be used for negative
        # values.
        is_negative = '-' in string[:m.start()]
        if not is_negative and parens_for_negatives:
            is_negative = '(' in string[:m.start()] and ')' in string[m.end():]
        if is_negative:
            value = -value
    return value

def parse_amount(
        string, default_currency=None, with_expression=True, auto_decimal_place=False,
        strict_currency=False):
    """Returns an :class:`Amount` from ``string``.

    We can parse strings like "42.54 cad" or "CAD 42.54".

    If ``default_currency`` is set, we can parse amounts that don't contain a currency code and will
    give the amount that currency.

    If ``with_expression`` is true, we can parse stuff like "42*4 cad" or "usd (1+2)/3". If you know
    your string doesn't contain any expression, turn this flag off to greatly speed up parsing.

    ``auto_decimal_place`` allows for quick decimal-less typing. We assume that the number has been
    typed to the last precision digit and automatically place our decimal separator if there isn't
    one. For example, "1234" would be parsed as "12.34" in a CAD context (in BHD, a currency with 3
    digits, it would be parsed as "1.234"). This doesn't work with expressions.

    With ``strict_currency`` enabled, ``UnsupportedCurrencyError`` is raised if an unsupported
    currency is specified. We still parse sucessfully if no currency is specified and
    ``default_currency`` is not ``None``.
    """
    if string is None or not string.strip():
        return 0

    currency = None
    m = re_currency.search(string)
    if m is not None:
        capture = m.group(0).upper()
        try:
            currency = Currencies.get(capture)
        except ValueError:
            if strict_currency:
                raise UnsupportedCurrencyError(capture)
        else:
            string = re_currency.sub('', string)
    currency = currency or default_currency
    exponent = currency.exponent if currency is not None else 2
    string = string.strip()
    # When we have an expression, we deal only with "simple" numbers. Turning expression off when
    # there's no sign of arithmetic operators allow for complex number parsing so that we can
    # correctly parse thousand separators.
    if with_expression and re_arithmetic_operators.search(string) is None:
        with_expression = False
    if with_expression:
        string = parse_amount_expression(string, exponent)
        try:
            value = eval(string)
        except (SyntaxError, ZeroDivisionError):
            raise ValueError('Invalid expression %r' % string)
        if not isinstance(value, (float, int)):
            raise ValueError('Invalid expression %r' % string)
        value = round(value, exponent)
    else:
        value = parse_amount_single(string, exponent, auto_decimal_place)
    if value == 0:
        return 0
    elif currency is not None:
        return Amount(value, currency)
    else:
        raise ValueError('No currency given')

def convert_amount(amount, target_currency, date):
    """Returns ``amount`` converted to ``target_currency`` using ``date`` exchange rates.

    :param amount: :class:`Amount`
    :param target_currency: :class:`.Currency`
    :param date: ``datetime.date``
    """
    if amount == 0:
        return amount
    currency = amount.currency
    if currency == target_currency:
        return amount
    exchange_rate = Currencies.get_rates_db().get_rate(
        date, currency.code, target_currency.code)
    return Amount(amount.value * exchange_rate, target_currency)

def prorate_amount(amount, spread_over_range, wanted_range):
    """Returns the prorated part of ``amount`` spread over ``spread_over_range`` for the ``wanted_range``.

    For example, if 100$ are spead over a range that lasts 10 days (let's say between the 10th and
    the 20th) and that there's an overlap of 4 days between ``spread_over_range`` and
    ``wanted_range`` (let's say the 16th and the 26th), the result will be 40$. Why? Because each
    day is worth 10$ and we're wanting the value of 4 of those days.

    :param amount: :class:`Amount`
    :param spread_over_range: :class:`.DateRange`
    :param wanted_range: :class:`.DateRange`
    """
    if not spread_over_range:
        return 0
    intersect = spread_over_range & wanted_range
    if not intersect:
        return 0
    rate = intersect.days / spread_over_range.days
    return amount * rate

def same_currency(amount1, amount2):
    return not (amount1 and amount2 and amount1.currency != amount2.currency)

def of_currency(amount, currency):
    return not amount or amount.currency == currency

