# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

import pytest
from ..testutil import eq_

from ...model.currency_provider.boc import BOCProvider

@pytest.mark.needs_network
def test_boc_currency_provider_EUR():
    provider = BOCProvider()
    rates = provider.get_currency_rates('EUR', date(2017, 8, 6), date(2017, 8, 12))
    EXPECTED = [
        (date(2017, 8, 8), 1.4911),
        (date(2017, 8, 9), 1.4916),
        (date(2017, 8, 10), 1.4936),
        (date(2017, 8, 11), 1.4984),

    ]
    eq_(rates, EXPECTED)

@pytest.mark.needs_network
def test_boc_currency_provider_historical_EUR():
    # historical rates fetching work too (before 2017, rates are fetched
    # differently)
    provider = BOCProvider()
    rates = provider.get_currency_rates('EUR', date(2016, 8, 6), date(2016, 8, 12))
    EXPECTED = [
        (date(2016, 8, 8), 1.4598),
        (date(2016, 8, 9), 1.4572),
        (date(2016, 8, 10), 1.4589),
        (date(2016, 8, 11), 1.4526),
        (date(2016, 8, 12), 1.4462),

    ]
    eq_(rates, EXPECTED)
