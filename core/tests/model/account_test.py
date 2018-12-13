# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from hscommon.testutil import eq_

from ...model.account import Account, Group, AccountList, AccountType, ACCOUNT_SORT_KEY
from ...model.amount import Amount
from ...model.currency import Currencies
from ...model.date import MonthRange
from ...model.oven import Oven
from ...model.transaction import Transaction
from ...model.transaction_list import TransactionList

class TestAccountComparison:
    def test_comparison(self):
        # Accounts are sorted by name. The sort is insensitive to case and accents.
        bell = Account('Bell', 'USD', AccountType.Asset)
        belarus = Account('Bélarus', 'USD', AccountType.Asset)
        achigan = Account('achigan', 'USD', AccountType.Asset)
        accounts = [bell, belarus, achigan]
        eq_(sorted(accounts, key=ACCOUNT_SORT_KEY), [achigan, belarus, bell])

    def test_equality(self):
        # Two different account objects are never equal.
        zoo1 = Account('Zoo', 'USD', AccountType.Asset)
        zoo2 = Account('Zoo', 'USD', AccountType.Asset)
        zoo3 = Account('Zoö', 'USD', AccountType.Asset)
        eq_(zoo1, zoo1)
        assert zoo1 != zoo2
        assert zoo1 != zoo3

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
        self.account = Account('Checking', 'USD', AccountType.Asset)
        accounts = AccountList('CAD')
        accounts.add(self.account)
        transactions = TransactionList([
            Transaction(date(2007, 12, 31), account=self.account, amount=Amount(20, 'USD')),
            Transaction(date(2008, 1, 1), account=self.account, amount=Amount(100, 'USD')),
            Transaction(date(2008, 1, 2), account=self.account, amount=Amount(50, 'USD')),
            Transaction(date(2008, 1, 3), account=self.account, amount=Amount(70, 'CAD')),
            Transaction(date(2008, 1, 31), account=self.account, amount=Amount(2, 'USD')),
        ])
        oven = Oven(accounts, transactions, [], [])
        oven.cook(date.min, date.max)

    def test_balance(self):
        eq_(
            self.account.balance(date(2007, 12, 31), self.account.currency),
            Amount(20, 'USD'))

        # The balance is converted using the rate on the day the balance is
        # requested.
        eq_(self.account.balance(date(2007, 12, 31), 'CAD'), Amount(20 * 1.1, 'CAD'))

    def test_cash_flow(self):
        range = MonthRange(date(2008, 1, 1))
        eq_(self.account.cash_flow(range, 'USD'), Amount(252, 'USD'))

        # Each entry is converted using the entry's day rate.
        eq_(self.account.cash_flow(range, 'CAD'), Amount(201.40, 'CAD'))

