# Copyright 2018 Virgil Dupras

# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# XXX This unit was previously "currency_test" from hscommon. During the merge into moneyguru core,
# I had to quickly find a place for it, but we could eventually merge this unit with its
# current currency_test neighbor.

from datetime import date

from hscommon.testutil import eq_, assert_almost_equal
from ...model.currency import Currencies, RatesDB

def setup_module(module):
    global FOO
    global BAR
    global PLN
    FOO = Currencies.register('FOO', 'Currency with start date', start_date=date(2009, 1, 12), start_rate=2)
    BAR = Currencies.register('BAR', 'Currency with stop date', stop_date=date(2010, 1, 12), latest_rate=2)
    PLN = Currencies.register('PLN', 'PLN')
    Currencies.set_rates_db(None)

def teardown_module(module):
    # We must unset our test currencies or else we might mess up with other tests.
    from ...model import currency
    import imp
    imp.reload(currency)

def teardown_function(function):
    Currencies.set_rates_db(None)

def test_get_rate_on_empty_db():
    # When there is no data available, use the latest rate.
    USD_LATEST_RATE = 1.0128
    Currencies.set_rates_db(None)
    eq_(Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD'), 1 / USD_LATEST_RATE)

def test_physical_rates_db_remember_rates(tmpdir):
    # When a rates db uses a real file, rates are remembered
    dbpath = str(tmpdir.join('foo.db'))
    db = RatesDB(dbpath)
    db.set_CAD_value(date(2008, 4, 20), 'USD', 1/0.996115)
    db = RatesDB(dbpath)
    assert_almost_equal(db.get_rate(date(2008, 4, 20), 'CAD', 'USD'), 0.996115, places=6)

def xtest_corrupt_db(tmpdir):
    # todo: cover this
    dbpath = str(tmpdir.join('foo.db'))
    fh = open(dbpath, 'w')
    fh.write('corrupted')
    fh.close()
    db = RatesDB(dbpath) # no crash. deletes the old file and start a new db
    db.set_CAD_value(date(2008, 4, 20), 'USD', 42)
    db = RatesDB(dbpath)
    assert_almost_equal(db.get_rate(date(2008, 4, 20), 'USD', 'CAD'), 42)

# --- Daily rate
def setup_daily_rate():
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/0.996115)

def test_get_rate_with_daily_rate():
    # Getting the rate exactly as set_rate happened returns the same rate.
    setup_daily_rate()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD')
    assert_almost_equal(rate, 0.996115, places=6)

def test_get_rate_different_currency():
    # Use fallback rates when necessary.
    setup_daily_rate()
    EUR_LATEST_RATE = 1.3298
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'EUR')
    assert_almost_equal(rate, 1 / EUR_LATEST_RATE, places=6)
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'EUR', 'USD')
    assert_almost_equal(rate, EUR_LATEST_RATE * 0.996115, places=6)

def test_get_rate_reverse():
    # It's possible to get the reverse value of a rate using the same data.
    setup_daily_rate()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'USD', 'CAD')
    assert_almost_equal(rate, 1 / 0.996115, places=6)

def test_set_rate_twice():
    # When setting a rate for an index that already exists, the old rate is replaced by the new.
    setup_daily_rate()
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/42)
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD')
    assert_almost_equal(rate, 42, places=2)

def test_set_rate_after_get():
    # When setting a rate after a get of the same rate, the rate cache is correctly updated.
    setup_daily_rate()
    # value will be cached
    Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD')
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/42)
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD')
    assert_almost_equal(rate, 42, places=2)

def test_set_rate_after_get_the_day_after():
    # When setting a rate, the cache for the whole currency is reset, or else we get old fallback
    # values for dates where the currency server returned no value.
    setup_daily_rate()
    # value will be cached
    Currencies.get_rates_db().get_rate(date(2008, 4, 21), 'CAD', 'USD')
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/42)
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 21), 'CAD', 'USD')
    assert_almost_equal(rate, 42, places=2)

# --- Two daily rates
def setup_two_daily_rate():
    # Don't change the set order, it's important for the tests
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 25), 'USD', 1/0.997115)
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/0.996115)

def test_date_range_range():
    # USD.rates_date_range() returns the USD's limits.
    setup_two_daily_rate()
    dr = Currencies.get_rates_db().date_range('USD')
    eq_(dr, (date(2008, 4, 20), date(2008, 4, 25)))

def test_date_range_for_unfetched_currency():
    # If the curency is not in the DB, return None.
    setup_two_daily_rate()
    dr = Currencies.get_rates_db().date_range('PLN')
    assert dr is None

def test_seek_rate_middle():
    # A rate request with seek in the middle will return the lowest date.
    setup_two_daily_rate()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'USD', 'CAD')
    assert_almost_equal(rate, 1 / 0.996115, places=6)

def test_seek_rate_after():
    # Make sure that the *nearest* lowest rate is returned. Because the 25th have been set
    # before the 20th, an order by clause is required in the seek SQL to make this test pass.
    setup_two_daily_rate()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 26), 'USD', 'CAD')
    assert_almost_equal(rate, 1 / 0.997115, places=6)

def test_seek_rate_before():
    # If there are no rate in the past, seek for a rate in the future.
    setup_two_daily_rate()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 19), 'USD', 'CAD')
    assert_almost_equal(rate, 1 / 0.996115, places=6)

# --- Rates of multiple currencies
def setup_rates_of_multiple_currencies():
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'USD', 1/0.996115)
    Currencies.get_rates_db().set_CAD_value(date(2008, 4, 20), 'EUR', 1/0.633141)

def test_get_rate_multiple_currencies():
    # Don't mix currency rates up.
    setup_rates_of_multiple_currencies()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'USD')
    assert_almost_equal(rate, 0.996115, places=6)
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'CAD', 'EUR')
    assert_almost_equal(rate, 0.633141, places=6)

def test_get_rate_with_pivotal():
    # It's possible to get a rate by using 2 records.
    # if 1 CAD = 0.996115 USD and 1 CAD = 0.633141 then 0.996115 USD = 0.633141 then 1 USD = 0.633141 / 0.996115 EUR
    setup_rates_of_multiple_currencies()
    rate = Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'USD', 'EUR')
    assert_almost_equal(rate, 0.633141 / 0.996115, places=6)

def test_get_rate_doesnt_exist():
    # Don't crash when trying to do pivotal calculation with non-existing currencies.
    setup_rates_of_multiple_currencies()
    Currencies.get_rates_db().get_rate(date(2008, 4, 20), 'USD', 'PLN') # no crash
