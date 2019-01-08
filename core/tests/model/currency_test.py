# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date, timedelta
import time

from pytest import raises
from ..testutil import jointhreads, eq_

from ...model.amount import convert_amount
from ...model.currency import (
    Currencies, RateProviderUnavailable, RatesDB)
from ...model.currency_provider import boc
from ..base import Amount

def slow_down(func):
    def wrapper(*args, **kwargs):
        time.sleep(0.1)
        return func(*args, **kwargs)

    return wrapper

def set_ratedb_for_tests(async_=False, slow_down_provider=False, provider=None):
    log = []

    # Returns a RatesDB that isn't async and that uses a fake provider
    def fake_provider(currency, start_date, end_date):
        log.append((start_date, end_date, currency))
        number_of_days = (end_date - start_date).days + 1
        return [(start_date + timedelta(i), 1.42 + (.01 * i)) for i in range(number_of_days)]

    db = RatesDB(':memory:', async_=async_)
    if provider is None:
        provider = fake_provider
    if slow_down_provider:
        provider = slow_down(provider)
    db.register_rate_provider(provider)
    Currencies.set_rates_db(db)
    return db, log

def test_unknown_currency():
    # Only known currencies are accepted.
    assert not Currencies.has('NOPE')

def test_async_and_repeat():
    # If you make an ensure_rates() call and then the same call right after (before the first one
    # is finished, the server will not be hit twice.
    db, log = set_ratedb_for_tests(async_=True, slow_down_provider=True)
    lastweek = date.today() - timedelta(days=7)
    db.ensure_rates(lastweek, ['USD'])
    db.ensure_rates(lastweek, ['USD'])
    jointhreads()
    eq_(len(log), 1)

def test_seek_rate():
    # Trying to get rate around the existing date gives the rate in question.
    set_ratedb_for_tests()
    Currencies.get_rates_db().set_CAD_value(date(2008, 5, 20), 'USD', 0.98)
    amount = Amount(42, 'USD')
    expected = Amount(42 * .98, 'CAD')
    eq_(convert_amount(amount, 'CAD', date(2008, 5, 21)), expected)
    eq_(convert_amount(amount, 'CAD', date(2008, 5, 19)), expected)

# ---
def test_ask_for_rates_in_the_past():
    # If a rate is asked for a date lower than the lowest fetched date, fetch that range.
    db, log = set_ratedb_for_tests()
    someday = date.today() - timedelta(days=4)
    db.ensure_rates(someday, ['USD']) # fetch some rates
    otherday = someday - timedelta(days=6)
    db.ensure_rates(otherday, ['USD']) # this one should also fetch rates
    eq_(len(log), 2)
    eq_(log[1], (otherday, someday - timedelta(days=1), 'USD'))

def test_ask_for_rates_in_the_future(monkeypatch):
    # If a rate is asked for a date equal or higher than the lowest fetched date, fetch cached_end - today.
    monkeypatch.patch_today(2008, 5, 30)
    db, log = set_ratedb_for_tests()
    db.set_CAD_value(date(2008, 5, 20), 'USD', 1.42)
    db.ensure_rates(date(2008, 5, 20), ['USD']) # this one should fetch 2008-5-21 up to today-1
    expected = [(date(2008, 5, 21), date(2008, 5, 29), 'USD')]
    eq_(log, expected)

def test_dont_crash_on_None_rates():
    # Don't crash when a currency provider returns None rates. Just ignore it.

    def provider(currency, start_date, end_date):
        return [(start_date, None)]

    db, log = set_ratedb_for_tests(provider=provider)
    db.ensure_rates(date(2008, 5, 20), ['USD']) # no crash
    db.get_rate(date(2008, 5, 20), 'USD', 'CAD') # no crash

def test_dont_cache_requests_in_the_future():
    # See issue #497
    # When receiving requests for rates in the future, we should shortcut our logic and completely
    # ignore the request. Previously, we would cache the request and, sometimes (in rare occasions)
    # we would get a request for datetime.max. Because this ended up in our cache and that datetime
    # arithmetic was performed on it, we would end up with an OverflowError. Avoid this.
    db, log = set_ratedb_for_tests()
    db.ensure_rates(date.max, ['USD'])
    db.ensure_rates(date(2017, 11, 4), ['USD']) # no crash

# --- Test for the default XMLRPC provider
def exception_raiser(exception):
    def f(*args, **kwargs):
        raise exception
    return f

def test_no_internet(monkeypatch):
    # No crash occur if the computer don't have access to internet.
    from socket import gaierror
    monkeypatch.setattr(boc, 'urlopen', exception_raiser(gaierror()))
    with raises(RateProviderUnavailable):
        boc.BOCProvider().wrapped_get_currency_rates(
            'USD', date(2008, 5, 20), date(2008, 5, 20)
        )

def test_connection_timeout(monkeypatch):
    # No crash occur the connection times out.
    from socket import error
    monkeypatch.setattr(boc, 'urlopen', exception_raiser(error()))
    with raises(RateProviderUnavailable):
        boc.BOCProvider().wrapped_get_currency_rates(
            'USD', date(2008, 5, 20), date(2008, 5, 20)
        )

