# Copyright 2018 Virgil Dupras

# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

"""This module facilitates currencies management. It exposes :class:`Currency` which lets you
easily figure out their exchange value.
"""

from datetime import date, timedelta
import logging
import threading
from queue import Queue, Empty

from . import _ccore

class CurrencyNotSupportedException(Exception):
    """The current exchange rate provider doesn't support the requested currency."""

class RateProviderUnavailable(Exception):
    """The rate provider is temporarily unavailable."""

class Currencies:
    all = []
    by_code = {}
    by_name = {}
    rates_db = None

    @classmethod
    def get(cls, code=None, name=None):
        """Returns the currency with the given code."""
        assert (code is None and name is not None) or (code is not None and name is None)
        if code is not None:
            code = code.upper()
            try:
                return cls.by_code[code]
            except KeyError:
                raise ValueError('Unknown currency code: %r' % code)
        else:
            try:
                return cls.by_name[name]
            except KeyError:
                raise ValueError('Unknown currency name: %r' % name)

    @staticmethod
    def has(code):
        try:
            Currencies.get(code)
            return True
        except ValueError:
            return False

    @staticmethod
    def register(
            code, name, exponent=2, start_date=None, start_rate=1, stop_date=None, latest_rate=1,
            priority=100):
        """Registers a new currency and returns it.

        ``priority`` determines the order of currencies in :meth:`all`. Lower priority goes first.
        """
        code = code.upper()
        if code in Currencies.by_code:
            return Currencies.by_code[code]
        assert name not in Currencies.by_name
        _ccore.currency_register(
            code, exponent, start_date, start_rate, stop_date, latest_rate)
        currency = _ccore.Currency(code)
        Currencies.by_code[code] = currency
        Currencies.by_name[name] = currency
        Currencies.all.append((currency, name, priority))
        return currency

    @staticmethod
    def reset_currencies():
        # Clear all currencies except USD, EUR and CAD because these are directly imported in too
        # many modules and we depend on those instances being present at too many places.
        # For now, this is only called during testing.
        Currencies.all = [(c, n, p) for (c, n, p) in Currencies.all if c.code in {'CAD', 'USD', 'EUR'}]
        Currencies.by_name = {n: c for (c, n, p) in Currencies.all}
        Currencies.by_code = {c.code: c for (c, n, p) in Currencies.all}
        Currencies.rates_db = None
        Currencies.sort_currencies()

    @staticmethod
    def set_rates_db(db):
        """Sets a new currency ``RatesDB`` instance to be used with all ``Currency`` instances.
        """
        Currencies.rates_db = db

    @staticmethod
    def get_rates_db():
        """Returns the current ``RatesDB`` instance.
        """
        if Currencies.rates_db is None:
            Currencies.rates_db = RatesDB() # Make sure we always have some db to work with
        return Currencies.rates_db

    @staticmethod
    def sort_currencies():
        Currencies.all = sorted(Currencies.all, key=lambda t: (t[2], t[0].code))


# For legacy purpose, we create USD, EUR and CAD in here, but all other currencies are app-defined.
Currencies.register(
    'USD', 'U.S. dollar',
    start_date=date(1998, 1, 2), start_rate=1.425, latest_rate=1.0128, priority=1
)
Currencies.register(
    'EUR', 'European Euro',
    start_date=date(1999, 1, 4), start_rate=1.8123, latest_rate=1.3298, priority=2
)
Currencies.register('CAD', 'Canadian dollar', latest_rate=1, priority=4)

class RatesDB:
    """Stores exchange rates for currencies.

    The currencies are identified with ISO 4217 code (USD, CAD, EUR, etc.).
    The rates are represented as float and represent the value of the currency in CAD.
    """
    def __init__(self, path=':memory:', async_=True):
        self._cache = {} # {(date, currency): CAD value
        _ccore.currency_global_init(path)
        self._rate_providers = []
        self.async_ = async_
        self._fetched_values = Queue()
        self._fetched_ranges = {} # a currency --> (start, end) map

    def _save_fetched_rates(self):
        while True:
            try:
                rates, currency, fetch_start, fetch_end = self._fetched_values.get_nowait()
                logging.debug("Saving %d rates for the currency %s", len(rates), currency)
                for rate_date, rate in rates:
                    if not rate:
                        logging.debug("Empty rate for %s. Skipping", rate_date)
                        continue
                    logging.debug("Saving rate %2.2f for %s", rate, rate_date)
                    self.set_CAD_value(rate_date, currency, rate)
                logging.debug("Finished saving rates for currency %s", currency)
            except Empty:
                break

    def clear_cache(self):
        self._cache = {}

    def date_range(self, currency_code):
        """Returns (start, end) of the cached rates for currency.

        Returns a tuple ``(start_date, end_date)`` representing dates covered in the database for
        currency ``currency_code``. If there are gaps, they are not accounted for (subclasses that
        automatically update themselves are not supposed to introduce gaps in the db).
        """
        return _ccore.currency_daterange(currency_code)

    def get_rate(self, date, currency1_code, currency2_code):
        """Returns the exchange rate between currency1 and currency2 for date.

        The rate returned means '1 unit of currency1 is worth X units of currency2'.
        The rate of the nearest date that is smaller than 'date' is returned. If
        there is none, a seek for a rate with a higher date will be made.
        """
        # We want to check self._fetched_values for rates to add.
        if not self._fetched_values.empty():
            self._save_fetched_rates()
        result = _ccore.currency_getrate(date, currency1_code, currency2_code)
        if result is None:
            # todo: either push "latest_rate" into ccore or get rid of this
            # concept.
            result = 1
        return result


    def set_CAD_value(self, date, currency_code, value):
        """Sets the daily value in CAD for currency at date"""
        # we must clear the whole cache because there might be other dates affected by this change
        # (dates when the currency server has no rates).
        self.clear_cache()
        _ccore.currency_set_CAD_value(date, currency_code, value)

    def register_rate_provider(self, rate_provider):
        """Adds `rate_provider` to the list of providers supported by this DB.

        A provider if a function(currency, start_date, end_date) that returns a list of
        (rate_date, float_rate) as a result. This function will be called asyncronously, so it's ok
        if it takes a long time to return.

        The rates returned must be the value of 1 `currency` in CAD (Canadian Dollars) at the
        specified date.

        The provider can be asked for any currency. If it doesn't support it, it has to raise
        CurrencyNotSupportedException.

        If we support the currency but that there is no rate available for the specified range,
        simply return an empty list or None.
        """
        self._rate_providers.append(rate_provider)

    def ensure_rates(self, start_date, currencies):
        """Ensures that the DB has all the rates it needs for 'currencies' between 'start_date' and today

        If there is any rate missing, a request will be made to the currency server. The requests
        are made asynchronously.
        """
        def do():
            for currency, fetch_start, fetch_end in currencies_and_range:
                logging.debug("Fetching rates for %s for date range %s to %s", currency, fetch_start, fetch_end)
                for rate_provider in self._rate_providers:
                    try:
                        values = rate_provider(currency, fetch_start, fetch_end)
                    except CurrencyNotSupportedException:
                        continue
                    except RateProviderUnavailable:
                        logging.warning("Fetching of %s failed due to temporary problems.", currency)
                        break
                    else:
                        if not values:
                            # We didn't get any value from the server, which means that we asked for
                            # rates that couldn't be delivered. Still, we report empty values so
                            # that the cache can correctly remember this unavailability so that we
                            # don't repeatedly fetch those ranges.
                            values = []
                        self._fetched_values.put((values, currency, fetch_start, fetch_end))
                        logging.debug("Fetching successful!")
                        break
                else:
                    logging.debug("Fetching failed!")

        if start_date >= date.today():
            return # we never return rates in the future
        currencies_and_range = []
        for currency in currencies:
            if currency == 'CAD':
                continue
            try:
                cached_range = self._fetched_ranges[currency]
            except KeyError:
                cached_range = self.date_range(currency)
            range_start = start_date
            # Don't try to fetch today's rate, it's never there and results in useless server
            # hitting.
            range_end = date.today() - timedelta(1)
            if cached_range is not None:
                cached_start, cached_end = cached_range
                if range_start >= cached_start:
                    # Make a forward fetch
                    range_start = cached_end + timedelta(days=1)
                else:
                    # Make a backward fetch
                    range_end = cached_start - timedelta(days=1)
            # We don't want to fetch ranges that are too big. It can cause various problems, such
            # as hangs. We prefer to take smaller bites.
            cur_start = cur_end = range_start
            while cur_end < range_end:
                cur_end = min(cur_end + timedelta(days=30), range_end)
                currencies_and_range.append((currency, cur_start, cur_end))
                cur_start = cur_end
            self._fetched_ranges[currency] = (start_date, date.today())
        if self.async_:
            threading.Thread(target=do).start()
        else:
            do()

def initialize_db(path):
    """Initialize the app wide currency db if not already initialized."""
    ratesdb = RatesDB(str(path))
    Currencies.set_rates_db(ratesdb)

