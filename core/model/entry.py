# Created By: Virgil Dupras
# Created On: 2010-07-29
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import bisect
import datetime
from collections import defaultdict, Sequence
from itertools import takewhile

from hscommon.util import flatten
from .amount import convert_amount, same_currency

class Entry:
    """Wrapper around a :class:`.Split` to show in an :class:`.Account` ledger.

    The two main roles of the entre as a wrapper is to handle user edits and show running totals
    for the account.

    It has its own :attr:`amount` because we might have to convert :attr:`.Split.amount` in another
    currency (the currency of the account, in which we'll want to display that amount).

    All initialization arguments are directly assigned to their relevant attributes in the entry.
    Most entries are created by the :class:`.Oven`, which does the necessary calculations to compute
    running total information that the entry needs on init.
    """
    def __init__(self, split, transaction, amount, balance, reconciled_balance, balance_with_budget):
        #: The :class:`.Split` our entry wraps.
        self.split = split
        self.transaction = transaction
        #: :class:`.Amount`. The amount of money that the entry moves.
        self.amount = amount
        #: :class:`.Amount`. The running total of all preceding entries in the account.
        self.balance = balance
        #: :class:`.Amount`. The running total of all preceding *reconciled* entries in the account.
        self.reconciled_balance = reconciled_balance
        #: :class:`.Amount`. Running balance which includes all :class:`.Budget` spawns.
        self.balance_with_budget = balance_with_budget
        #: ``int``. Index in the EntryList. Set by :meth:`EntryList.add_entry` and used as a tie
        #: breaker in case we have more than one entry from the same transaction.
        self.index = -1

    def __eq__(self, other):
        if other is None:
            return False
        return self.split == other.split

    def __hash__(self):
        return hash(self.split)

    def __repr__(self):
        return '<Entry %r %r>' % (self.date, self.description)

    def change_amount(self, amount):
        """Change the amount of :attr:`split`, from the perspective of the account ledger.

        This can only be done if the :class:`.Transaction` to which we belong is a two-way
        transaction. This will trigger a two-way :meth:`balancing <.Transaction.balance>`.

        :param amount: :class:`.Amount` to change our entry to.
        """
        assert len(self.splits) == 1
        self.split.amount = amount
        other_split = self.splits[0]
        is_mct = False
        if not same_currency(amount, other_split.amount):
            is_asset = self.account is not None and self.account.is_balance_sheet_account()
            other_is_asset = other_split.account is not None and other_split.account.is_balance_sheet_account()
            if is_asset and other_is_asset:
                is_mct = True
        if is_mct: # don't touch other side unless we have a logical imbalance
            if self.split.is_on_same_side(other_split):
                other_split.amount *= -1
        else:
            other_split.amount = -amount

    def normal_balance(self):
        """:attr:`balance`, with inverted sign if account is liability or income.

        .. seealso:: :meth:`.Account.normalize_amount`
        """
        is_credit = self.account is not None and self.account.is_credit_account()
        return -self.balance if is_credit else self.balance

    @property
    def account(self):
        """*readonly*. Proxy to :attr:`.Split.account`."""
        return self.split.account

    @property
    def checkno(self):
        """*readonly*. Proxy to :attr:`.Transaction.checkno`."""
        return self.transaction.checkno

    @property
    def date(self):
        """*readonly*. Proxy to :attr:`.Transaction.date`."""
        return self.transaction.date

    @property
    def description(self):
        """*readonly*. Proxy to :attr:`.Transaction.description`."""
        return self.transaction.description

    @property
    def payee(self):
        """*readonly*. Proxy to :attr:`.Transaction.payee`."""
        return self.transaction.payee

    @property
    def mtime(self):
        """*readonly*. Proxy to :attr:`.Transaction.mtime`."""
        return self.transaction.mtime

    @property
    def splits(self):
        """*readonly*. A list of all other splits in :attr:`transaction` except the one we wrap."""
        return [s for s in self.transaction.splits if s is not self.split]

    @property
    def transfer(self):
        """*readonly*. A list of the :class:`accounts <.Account>` in :attr:`splits`."""
        return [split.account for split in self.splits if split.account is not None]

    @property
    def reconciled(self):
        """*readonly*. Proxy to :attr:`.Split.reconciled`."""
        return self.split.reconciled

    @property
    def reconciliation_date(self):
        """*readonly*. Proxy to :attr:`.Split.reconciliation_date`."""
        return self.split.reconciliation_date

    @property
    def reconciliation_key(self):
        """*readonly*. Sort key to use to know which entry was the last to be reconciled."""
        recdate = self.reconciliation_date
        if recdate is None:
            recdate = datetime.date.min
        return (recdate, self.date, self.transaction.position, self.index)

    @property
    def reference(self):
        """*readonly*. Proxy to :attr:`.Split.reference`."""
        return self.split.reference


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

