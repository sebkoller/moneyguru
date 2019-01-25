# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# The code difference between the various account related pie chart is way too small, that's why
# they're all grouped here.

from collections import defaultdict
from core.trans import tr
from ..const import AccountType
from .pie_chart import PieChart

class _AccountPieChart(PieChart):
    def __init__(self, parent_view, title):
        PieChart.__init__(self, parent_view)
        self._title = title

    # --- Protected
    def _get_account_data(self, accounts): # Virtual
        raise NotImplementedError()

    def _get_data_for_account_type(self, account_type): # Override
        accounts = self._accounts(account_type)
        account_data = self._get_account_data(accounts)
        data = defaultdict(int)
        for account, amount in account_data:
            name = account.name
            if account.groupname and not self.parent_view.is_group_expanded(account.groupname, account.type):
                name = account.groupname
            data[name] += amount
        return data

    def _accounts(self, account_type):
        accounts = {a for a in self.document.accounts if a.type == account_type}
        return accounts - self.document.excluded_accounts

    # --- Properties
    @property
    def title(self):
        return self._title


class BalancePieChart(_AccountPieChart):
    def __init__(self, networth_view):
        _AccountPieChart.__init__(self, networth_view, tr('Assets & Liabilities'))

    # --- Override
    def _get_account_data(self, accounts):
        date = self.document.date_range.end
        currency = self.document.default_currency

        def get_value(account):
            entries = self.document.accounts.entries_for_account(account)
            balance = entries.normal_balance(date, currency)
            return balance

        return [(a, get_value(a)) for a in accounts]

    def _get_data(self):
        return (
            self._get_data_for_account_type(AccountType.Asset),
            self._get_data_for_account_type(AccountType.Liability)
        )

class CashFlowPieChart(_AccountPieChart):
    def __init__(self, profit_view):
        _AccountPieChart.__init__(self, profit_view, tr('Income & Expenses'))

    # --- Override
    def _get_account_data(self, accounts):
        date_range = self.document.date_range
        currency = self.document.default_currency

        def get_value(account):
            entries = self.document.accounts.entries_for_account(account)
            cash_flow = entries.normal_cash_flow(date_range, currency)
            budgeted = self.document.budgets.normal_amount_for_account(account, date_range, currency=currency)
            return cash_flow + budgeted

        return [(a, get_value(a)) for a in accounts]

    def _get_data(self):
        return (
            self._get_data_for_account_type(AccountType.Income),
            self._get_data_for_account_type(AccountType.Expense)
        )

