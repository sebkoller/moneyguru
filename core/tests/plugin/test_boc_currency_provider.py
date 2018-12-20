# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

import pytest
from ..testutil import eq_

from ...plugin.boc_currency_provider import BOCProviderPlugin

@pytest.mark.needs_network
def test_boc_currency_provider_EUR():
    provider = BOCProviderPlugin()
    rates = provider.get_currency_rates('EUR', date(2017, 8, 6), date(2017, 8, 12))
    EXPECTED = [
        (date(2017, 8, 8), 1.4911),
        (date(2017, 8, 9), 1.4916),
        (date(2017, 8, 10), 1.4936),
        (date(2017, 8, 11), 1.4984),

    ]
    eq_(rates, EXPECTED)

