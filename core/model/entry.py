# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import bisect
from collections import defaultdict, Sequence
from itertools import takewhile

from hscommon.util import flatten
from .amount import convert_amount

class EntryList(Sequence):
    """Manages the :class:`Entry` list for an :class:`.Account`.

    The main roles of this class is to manage entry order as well as managing "last entries" to be
    able to easily answer questions like "What's the running total of the last entry at date X?"

    :param account: :class:`.Account` for which we manage entries.
    """
    def __init__(self, account):
        #: :class:`.Account` for which we manage entries.
        self.account = account
        self._entries = []
        self._date2entries = defaultdict(list)
        self._sorted_entry_dates = []
        # the key for this dict is (date_range, currency)
        self._daterange2cashflow = {}
        self._last_reconciled = None

    def __getitem__(self, key):
        return self._entries.__getitem__(key)

    def __len__(self):
        return len(self._entries)

    # --- Private
    def _balance(self, balance_attr, date=None, currency=None):
        entry = self.last_entry(date) if date else self.last_entry()
        if entry:
            balance = getattr(entry, balance_attr)
            if currency:
                return convert_amount(balance, currency, date)
            else:
                return balance
        else:
            return 0

    def _cash_flow(self, date_range, currency):
        cache = self._date2entries
        entries = flatten(cache[date] for date in date_range if date in cache)
        entries = (e for e in entries if not getattr(e.transaction, 'is_budget', False))
        amounts = (convert_amount(e.amount, currency, e.date) for e in entries)
        return sum(amounts)

    # --- Public
    def add_entry(self, entry):
        """Add ``entry`` to the list.

        add_entry() calls must *always* be made in order (this is called pretty much only by the
        :class:`.Oven`).
        """
        entry.index = len(self)
        self._entries.append(entry)
        date = entry.date
        self._date2entries[date].append(entry)
        if not self._sorted_entry_dates or self._sorted_entry_dates[-1] < date:
            self._sorted_entry_dates.append(date)
        if (self._last_reconciled is None) or (entry.reconciliation_key >= self._last_reconciled.reconciliation_key):
            self._last_reconciled = entry

    def balance(self, date=None, currency=None):
        """Returns running balance for :attr:`account` at ``date``.

        If ``currency`` is specified, the result is :func:`converted <.convert_amount>`.

        :param date: ``datetime.date``
        :param currency: :class:`.Currency`
        """
        return self._balance('balance', date, currency=currency)

    def balance_of_reconciled(self):
        """Returns :attr:`Entry.reconciled_balance` for our last reconciled entry."""
        entry = self._last_reconciled
        if entry is not None:
            return entry.reconciled_balance
        else:
            return 0

    def balance_with_budget(self, date=None, currency=None):
        """Same as :meth:`balance`, but including :class:`.Budget` spawns."""
        return self._balance('balance_with_budget', date, currency=currency)

    def cash_flow(self, date_range, currency=None):
        """Returns the sum of entry amounts occuring in ``date_range``.

        If ``currency`` is specified, the result is :func:`converted <.convert_amount>`.

        :param date_range: :class:`.DateRange`
        :param currency: :class:`.Currency`
        """
        currency = currency or self.account.currency
        cache_key = (date_range, currency)
        if cache_key not in self._daterange2cashflow:
            cash_flow = self._cash_flow(date_range, currency)
            self._daterange2cashflow[cache_key] = cash_flow
        return self._daterange2cashflow[cache_key]

    def clear(self, from_date):
        """Remove all entries from ``from_date``."""
        if from_date is None:
            self._entries = []
        else:
            self._entries = list(takewhile(lambda e: e.date < from_date, self._entries))
        if self._entries:
            index = bisect.bisect_left(self._sorted_entry_dates, from_date)
            for date in self._sorted_entry_dates[index:]:
                del self._date2entries[date]
            for date_range, currency in list(self._daterange2cashflow.keys()):
                if date_range.end >= from_date:
                    del self._daterange2cashflow[(date_range, currency)]
            del self._sorted_entry_dates[index:]
            self._last_reconciled = max(self._entries, key=lambda e: e.reconciliation_key)
        else:
            self._date2entries = defaultdict(list)
            self._daterange2cashflow = {}
            self._sorted_entry_dates = []
            self._last_reconciled = None

    def last_entry(self, date=None):
        """Return the last entry with a date that isn't after ``date``.

        If ``date`` isn't specified, returns the last entry in the list.
        """
        if self._entries:
            if date is None:
                return self._entries[-1]
            else:
                if date not in self._date2entries: # find the nearest smaller date
                    index = bisect.bisect_right(self._sorted_entry_dates, date) - 1
                    if index < 0:
                        return None
                    date = self._sorted_entry_dates[index]
                return self._date2entries[date][-1]
        return None

    def normal_balance(self, date=None, currency=None):
        """Returns a :meth:`normalized <.Account.normalize_amount>` :meth:`balance`."""
        balance = self.balance(date=date, currency=currency)
        return self.account.normalize_amount(balance)

    def normal_balance_of_reconciled(self):
        """Returns a :meth:`normalized <.Account.normalize_amount>` :meth:`balance_of_reconciled`.
        """
        balance = self.balance_of_reconciled()
        return self.account.normalize_amount(balance)

    def normal_cash_flow(self, date_range, currency=None):
        """Returns a :meth:`normalized <.Account.normalize_amount>` :meth:`cash_flow`."""
        cash_flow = self.cash_flow(date_range, currency)
        return self.account.normalize_amount(cash_flow)

