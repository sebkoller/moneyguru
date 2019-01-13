# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from ..testutil import eq_

from ...model._ccore import AccountList, TransactionList
from ...model.account import Group, AccountType, ACCOUNT_SORT_KEY
from ...model.currency import Currencies
from ...model.date import MonthRange
from ...model.oven import Oven
from ...model.transaction import Transaction
from ..base import Amount

class TestAccountComparison:
    def test_comparison(self):
        # Accounts are sorted by name. The sort is insensitive to case and accents.
        l = AccountList('USD')
        bell = l.create('Bell', 'USD', AccountType.Asset)
        belarus = l.create('Bélarus', 'USD', AccountType.Asset)
        achigan = l.create('achigan', 'USD', AccountType.Asset)
        accounts = [bell, belarus, achigan]
        eq_(sorted(accounts, key=ACCOUNT_SORT_KEY), [achigan, belarus, bell])


class TestGroupComparison:
    def test_comparison(self):
        # Groups are sorted by name. The sort is insensitive to case and accents.
        bell = Group('Bell', AccountType.Asset)
        belarus = Group('Bélarus', AccountType.Asset)
        achigan = Group('achigan', AccountType.Asset)
        groups = [bell, belarus, achigan]
        eq_(sorted(groups), [achigan, belarus, bell])

    def test_equality(self):
        # Two different group objects are never equal.
        zoo1 = Group('Zoo', AccountType.Asset)
        zoo2 = Group('Zoo', AccountType.Asset)
        zoo3 = Group('Zoö', AccountType.Asset)
        eq_(zoo1, zoo1)
        assert zoo1 != zoo2
        assert zoo1 != zoo3


class TestOneAccount:
    def setup_method(self, method):
        Currencies.get_rates_db().set_CAD_value(date(2007, 12, 31), 'USD', 1.1)
        Currencies.get_rates_db().set_CAD_value(date(2008, 1, 1), 'USD', 0.9)
        Currencies.get_rates_db().set_CAD_value(date(2008, 1, 2), 'USD', 0.8)
        Currencies.get_rates_db().set_CAD_value(date(2008, 1, 3), 'USD', 0.7)
        self.accounts = AccountList('CAD')
        self.account = self.accounts.create('Checking', 'USD', AccountType.Asset)
        txns = [
            Transaction(date(2007, 12, 31), account=self.account, amount=Amount(20, 'USD')),
            Transaction(date(2008, 1, 1), account=self.account, amount=Amount(100, 'USD')),
            Transaction(date(2008, 1, 2), account=self.account, amount=Amount(50, 'USD')),
            Transaction(date(2008, 1, 3), account=self.account, amount=Amount(70, 'CAD')),
            Transaction(date(2008, 1, 31), account=self.account, amount=Amount(2, 'USD')),
        ]
        transactions = TransactionList()
        for txn in txns:
            transactions.add(txn)
        self.oven = Oven(self.accounts, transactions, [], [])
        self.oven.cook(date.min, date.max)

    def test_balance(self):
        entries = self.accounts.entries_for_account(self.account)
        eq_(
            entries.balance(date(2007, 12, 31), self.account.currency),
            Amount(20, 'USD'))

        # The balance is converted using the rate on the day the balance is
        # requested.
        eq_(entries.balance(date(2007, 12, 31), 'CAD'), Amount(20 * 1.1, 'CAD'))

    def test_cash_flow(self):
        entries = self.accounts.entries_for_account(self.account)
        range = MonthRange(date(2008, 1, 1))
        eq_(entries.cash_flow(range, 'USD'), Amount(252, 'USD'))

        # Each entry is converted using the entry's day rate.
        eq_(entries.cash_flow(range, 'CAD'), Amount(201.40, 'CAD'))

def test_accountlist_contains():
    # AccountList membership is based on account name, not Account instances.
    # Account name tests are exact though, so it's not the exact same thing
    # as in find()
    al1 = AccountList('CAD')
    a1 = al1.create('foo', 'CAD', AccountType.Asset)
    a2 = al1.create('bar', 'CAD', AccountType.Asset)
    al2 = AccountList('CAD')
    a3 = al2.create('foo', 'CAD', AccountType.Asset)
    assert a1 in al1
    assert a1 in al2
    assert a2 in al1
    assert a2 not in al2
    assert a3 in al1
    assert a3 in al2
