# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import copy
from collections import defaultdict
from datetime import date

from core.util import extract

from ._ccore import inc_date
from .amount import prorate_amount
from .date import DateRange, ONE_DAY
from .recurrence import get_repeat_type_desc, Spawn, DateCounter, RepeatType
from .transaction import Transaction

class Budget:
    """Regular budget for a specific account.

    A budgets yields spawns with amounts depending on how much money we've already spent in our
    account. For example, if I have a monthly budget of 100$ for "Clothing", then the budget spawn
    for a month that has 25$ worth of clothing in it is going to be 75$. This only works in the
    future.

    Budgets work very similarly to recurrences, except that a twist must be applied to them so they
    can work properly. The twist is about the spawn's "recurrence" date and the effective date. The
    recurrence date must be at the beginning of the period, but the effective date must be at the end
    of it. The reason for it is that since recurrence are only cooked until a certain date (usually
    the current date range's end), but that the budget is affects the date range *prior* to it, the
    last budget of the date range will never be represented.

    All initialization variables are directly assigned to their corresponding attributes.

    Subclasses :class:`.Recurrence`.

    .. seealso:: :doc:`/forecast`
    """
    def __init__(self, account, amount):
        #: :class:`.Account` for which we budget. Has to be an income or expense.
        self.account = account
        #: The :class:`.Amount` we budget for our time span.
        self.amount = amount
        #: ``str``. Freeform notes from the user.
        self.notes = ''
        self._previous_spawns = []

    def __repr__(self):
        return '<Budget %r %r>' % (self.account, self.amount)

    # --- Public
    def replicate(self):
        result = copy.copy(self)
        return result

    def get_spawns(self, start_date, repeat_type, repeat_every, end, transactions, consumedtxns):
        date_counter = DateCounter(start_date, repeat_type, repeat_every, end)
        spawns = []
        current_ref = Transaction(start_date)
        for current_date in date_counter:
            # `recurrence_date` is the date at which the budget *starts*.
            # We need a date counter to see which date is next (so we can know when our period ends
            end_date = inc_date(current_date, repeat_type, repeat_every) - ONE_DAY
            if end_date <= date.today():
                # No spawn in the past
                continue
            spawn = Spawn(
                self, current_ref, recurrence_date=current_date, date=end_date,
                txntype=3)
            spawns.append(spawn)
        account = self.account
        budget_amount = self.amount if account.is_debit_account() else -self.amount
        relevant_transactions = set(t for t in transactions if account in t.affected_accounts())
        relevant_transactions -= consumedtxns
        for spawn in spawns:
            affects_spawn = lambda t: spawn.recurrence_date <= t.date <= spawn.date
            wheat, shaft = extract(affects_spawn, relevant_transactions)
            relevant_transactions = shaft
            txns_amount = sum(t.amount_for_account(account, budget_amount.currency_code) for t in wheat)
            if abs(txns_amount) < abs(budget_amount):
                spawn_amount = budget_amount - txns_amount
                if spawn.amount_for_account(account, budget_amount.currency_code) != spawn_amount:
                    spawn.change(amount=spawn_amount, from_=account, to=None)
            else:
                spawn.change(amount=0, from_=account, to=None)
            consumedtxns |= set(wheat)
        self._previous_spawns = spawns
        return spawns

    # --- Public
    def amount_for_date_range(self, date_range, currency):
        """Returns the budgeted amount for ``date_range``.

        That is, the pro-rated amount we're currently budgeting (with adjustments for transactions
        "consuming" the budget) for the date range.

        **Warning:** :meth:`get_spawns` must have been called until a date high enough to cover our
        date range. We're using previously generated spawns to compute that amount.

        :param date_range: The date range we want our budgeted amount for.
        :type date_range: :class:`.DateRange`
        :param currency: The currency of the returned amount. If the amount for the budget is
                         different, the exchange rate for the date of the beggining of the budget
                         spawn is used.
        :type currency: :class:`.Currency`
        :rtype: :class:`.Amount`
        """
        total_amount = 0
        for spawn in self._previous_spawns:
            amount = spawn.amount_for_account(self.account, currency)
            if not amount:
                continue
            my_start_date = max(spawn.recurrence_date, date.today() + ONE_DAY)
            my_end_date = spawn.date
            my_date_range = DateRange(my_start_date, my_end_date)
            total_amount += prorate_amount(amount, my_date_range, date_range)
        return total_amount


class BudgetList(list):
    """Manage the collection of budgets of a document.

    This subclasses ``list`` and provides a few methods for getting stats for all budgets in the
    list.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.start_date = date.today()
        self.repeat_type = RepeatType.Monthly
        self.repeat_every = 1
        self.repeat_type_desc = get_repeat_type_desc(self.repeat_type, self.start_date)

    def amount_for_account(self, account, date_range, currency=None):
        """Returns the amount for all budgets for ``account``.

        In short, we sum up the result of :meth:`Budget.amount_for_date_range` calls.

        :param account: The account we want to count our budget for.
        :type account: :class:`.Account`
        :param date_range: The date range we want our budgeted amount for.
        :type date_range: :class:`.DateRange`
        :param currency: The currency of the returned amount. If ``None``, we use the currency of
                         ``account``.
        :type currency: :class:`.Currency`
        :rtype: :class:`.Amount`
        """
        if not date_range.future:
            return 0
        budgets = [b for b in self if b.account == account and b.amount]
        if not budgets:
            return 0
        currency = currency or account.currency
        amount = sum(b.amount_for_date_range(date_range, currency) for b in budgets)
        return amount

    def normal_amount_for_account(self, account, date_range, currency=None):
        """Normalized version of :meth:`amount_for_account`.

        .. seealso:: :meth:`core.model.account.Account.normalize_amount`
        """
        budgeted_amount = self.amount_for_account(account, date_range, currency)
        return account.normalize_amount(budgeted_amount)

    def get_spawns(self, until_date, txns):
        if not self:
            return []
        start_date = self.start_date
        repeat_type = self.repeat_type
        repeat_every = self.repeat_every
        result = []
        # It's possible to have 2 budgets overlapping in date range and having the same account
        # When it happens, we need to keep track of which budget "consume" which txns
        account2consumedtxns = defaultdict(set)
        for budget in self:
            if not budget.amount:
                continue
            consumedtxns = account2consumedtxns[budget.account]
            spawns = budget.get_spawns(start_date, repeat_type, repeat_every, until_date, txns, consumedtxns)
            spawns = [spawn for spawn in spawns if not spawn.is_null]
            result += spawns
        return result

