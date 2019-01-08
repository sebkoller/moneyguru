# Copyright 2019 Virgil Dupras

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
    # For legacy purpose, we create USD, EUR and CAD in here, but all other
    # currencies are app-defined.
    all = [
        ('USD', 'U.S. dollar', 1),
        ('EUR', 'European Euro', 2),
        ('CAD', 'Canadian dollar', 4),
    ]
    codes = {t[0] for t in all}
    rates_db = None

    @classmethod
    def has(cls, code):
        return code.upper() in cls.codes
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
        if Currencies.has(code):
            return
        _ccore.currency_register(
            code, exponent, start_date, start_rate, stop_date, latest_rate)
        Currencies.codes.add(code)
        Currencies.all.append((code, name, priority))

    @staticmethod
    def reset_currencies():
        # Clear all currencies except USD, EUR and CAD because these are directly imported in too
        # many modules and we depend on those instances being present at too many places.
        # For now, this is only called during testing.
        _ccore.currency_global_reset_currencies()
        Currencies.codes = {'CAD', 'USD', 'EUR'}
        Currencies.all = [(c, n, p) for (c, n, p) in Currencies.all if c in Currencies.codes]
        Currencies.rates_db = None
        Currencies.sort_currencies()

    @classmethod
    def display_list(cls):
        return ['%s - %s' % (c, n) for c, n, p in cls.all]

    @classmethod
    def index(cls, code):
        for i, (c, n, p) in enumerate(cls.all):
            if c == code:
                return i
        raise IndexError()

    @classmethod
    def code_at_index(cls, index):
        if index < 0:
            raise IndexError()
        return Currencies.all[index][0]

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
        Currencies.all = sorted(Currencies.all, key=lambda t: (t[2], t[0]))


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

        if not self._rate_providers:
            logging.debug("No rate provider, can't ensure_rates")
            return
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

class CurrencyProvider:
    """Allows the creation of new currencies and the fetching of their rates.

    By subclassing this provider, you can add new currencies to moneyGuru and
    also add a new source to fetch those currencies' exchange rates.
    """
    def __init__(self):
        self.supported_currency_codes = set()
        try:
            for code, name, exponent, fallback_rate in self.register_currencies():
                self.register_currency(code, name, exponent=exponent, latest_rate=fallback_rate)
        except TypeError: # We return None, which means we registered all currencies manually.
            pass
        Currencies.sort_currencies()

    def wrapped_get_currency_rates(self, currency_code, start_date, end_date):
        """Tries to fetch exchange rates for ``currency_code``.

        If our currency is supported by our provider, we first try the "simple" fetching
        (:meth:`get_currency_rate_today`). If it's not implemented, we try the "complex" one
        (:meth:`get_currency_rates`). We return the result of the first method to work.

        If we can't get results, either because our currency isn't supported or because our
        implementation is incomplete, :exc:`.CurrencyNotSupportedException` is raised.

        This method isn't designed to be overriden.
        """
        if currency_code not in self.supported_currency_codes:
            raise CurrencyNotSupportedException()
        try:
            simple_result = self.get_currency_rate_today(currency_code)
            if simple_result is not None:
                return [(date.today(), simple_result)]
            else:
                return []
        except NotImplementedError:
            try:
                return self.get_currency_rates(currency_code, start_date, end_date)
            except NotImplementedError:
                raise CurrencyNotSupportedException()

    def register_currency(self, code, name, **kwargs):
        """Register a currency.

        Calling this gives more options than the simple return scheme of :meth:`register_currencies`.

        ``**kwargs`` is passed directly to :meth:`Currency.register`.

        Returns the resulting currency instance.
        """
        result = Currencies.register(code, name, **kwargs)
        self.supported_currency_codes.add(code)
        return result

    def register_currencies(self):
        """Override this and return a list of new currencies to support.

        The expected return value is a list of tuples ``(code, name, exponent, fallback_rate)``.

        If you need to set more option, call :meth:`register_currency` instead.

        ``exponent`` is the number of decimal numbers that should be displayed when formatting
        amounts in this currency.

        ``fallback_rate`` is the rate to use in case we can't fetch a rate. You can use the rate
        that is in effect when you write the provider. Of course, it will become wildly innaccurate
        over time, but it's still better than a rate of ``1``.
        """
        raise NotImplementedError()

    def get_currency_rate_today(self, currency_code):
        """Override this if you have a 'simple' provider.

        If your provider doesn't give rates for any other date than today, overriding this method
        instead of get_currency_rate() is the simplest choice.

        ``currency_code`` is a string representing the code of the currency to fetch, 'USD' for
        example.

        Return a float representing the value of 1 unit of your currency in CAD.

        If you can't get a rate, return ``None``.

        This method is called asynchronously, so it won't block moneyGuru if it takes time to
        resolve.
        """
        raise NotImplementedError()

    def get_currency_rates(self, currency_code, start_date, end_date):
        """Override this if your provider gives rates for past dates.

        If your provider gives rates for past dates, it's better (although a bit more complicated)
        to override this method so that moneyGuru can have more accurate rates.

        You must return a list of tuples (date, rate) with all rates you can fetch between
        start_date and end_date. You don't need to have one item for every single date in the range
        (for example, most of the time we don't have values during week-ends), moneyGuru correctly
        handles holes in those values. Simply return whatever you can get.

        If you can't get a rate, return an empty list.

        This method is called asynchronously, so it won't block moneyGuru if it takes time to
        resolve.
        """
        raise NotImplementedError()

