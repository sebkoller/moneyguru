# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ._ccore import ( # noqa
    amount_format as format_amount, amount_parse as parse_amount,
    amount_convert as convert_amount,
    UnsupportedCurrencyError)


# Temporary helper
def is_amount(a):
    from ._ccore import Amount
    return isinstance(a, Amount)

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
    return not (amount1 and amount2 and amount1.currency_code != amount2.currency_code)

def of_currency(amount, currency):
    return not amount or amount.currency_code == currency

