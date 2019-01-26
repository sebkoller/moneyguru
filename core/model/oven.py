# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date
from itertools import dropwhile
from operator import attrgetter

from core.util import flatten

from ._ccore import oven_cook_txns
from .budget import BudgetList

class Oven:
    """Computes raw data from transactions, schedules, budgets.

    Two main things the oven :ref:`cooks <cooking>`:

    1. Spawns schedule and budget transactions and insert them into its cooked result,
       :attr:`transactions`. This :class:`.TransactionList` is what is then used by the rest of the
       app to display transactions and account entries.
    2. Creates :class:`.Entry` instances to place in :attr:`.Account.entries`. These entries contain
       running totals for each account (which is, of course, calculated).
    """
    def __init__(self, accounts, transactions, scheduled, budgets):
        self._accounts = accounts
        self._transactions = transactions
        self._scheduled = scheduled
        self._budgets = budgets
        self._cooked_until = date.min
        #: List of cooked transactions, containing :class:`.Transaction` instances mixed with
        #: schedule and budget :class:`.Spawn` instances (in date/position order).
        self.transactions = []

    def _budget_spawns(self, until_date, schedule_spawns):
        if not self._budgets:
            return []
        # TODO: fix this
        if not isinstance(self._budgets, BudgetList):
            self._budgets = BudgetList(self._budgets)
        ref_date = self._budgets.start_date
        relevant_txns = list(dropwhile(lambda t: t.date < ref_date, self._transactions)) + schedule_spawns
        return self._budgets.get_spawns(until_date, relevant_txns)

    def continue_cooking(self, until_date):
        """Cooks from where we stop last time until ``until_date``.

        Cooking dates are often determined by the current date range, so when we advance or enlarge
        our date range, we usually need to cook a bit further than where we stopped last time.

        This is what this method is about.
        """
        if until_date > self._cooked_until:
            self.cook(self._cooked_until, until_date)

    def cook(self, from_date=None, until_date=None):
        """Cooks raw data into :attr:`transactions`.

        :param from_date: when set, saves calculation time by re-using existing cooked transactions.
        :type from_date: ``datetime.date``
        :param until_date: because of recurrence, we must always have a date at which we stop
                           cooking. If we don't, we might end up in an infinite loop. If not set,
                           will be the date of the transaction with the highest date.
        :type until_date: ``datetime.date``
        """
        # Determine from/until dates
        if from_date is None:
            from_date = date.min
        else:
            # it's possible that we have to reduce from_date a bit. If a split from before as a
            # reconciled date >= from_date, we have to set from_date to that split's normal date
            # We reverse the transactions to correctly detect chained overlappings in date/recdate
            for txn in reversed(self.transactions): # splits from *cooked* txns
                for split in txn.splits:
                    rdate = split.reconciliation_date
                    if rdate is not None and rdate >= from_date:
                        from_date = min(from_date, txn.date)
        self._transactions.sort() # needed in case until_date is None
        if until_date is None:
            until_date = self._transactions.last().date if self._transactions else from_date
        # Clear old cooked data
        for account in self._accounts:
            entries = self._accounts.entries_for_account(account)
            entries.clear(from_date)
        if from_date == date.min:
            self.transactions = []
        else:
            self.transactions = [t for t in self.transactions if t.date < from_date]
        # Cook
        if self._scheduled is not None:
            spawns = flatten(recurrence.get_spawns(until_date) for recurrence in self._scheduled)
            spawns += self._budget_spawns(until_date, spawns)
            # To ensure that our sort order stay correct and consistent, we assign position values
            # to our spawns. To ensure that there's no overlap, we start our position counter at
            # len(transactions)
            for counter, spawn in enumerate(spawns, start=len(self._transactions)):
                spawn.position = counter
        else:
            spawns = []
        txns = list(self._transactions) + spawns
        # we don't filter out txns > until_date because they might be budgets affecting current data
        # XXX now that budget's base date is the start date, isn't this untrue?
        tocook = [t for t in txns if from_date <= t.date]
        tocook.sort(key=attrgetter('date'))
        oven_cook_txns(self._accounts, tocook)
        self.transactions += tocook
        self._cooked_until = until_date

