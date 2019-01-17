# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr
from ..model.date import DateRange
from .balance_graph import BalanceGraph

class NetWorthGraph(BalanceGraph):
    def __init__(self, networth_view):
        BalanceGraph.__init__(self, networth_view)

    def _balance_for_date(self, date):
        def bal(a):
            entries = self.document.accounts.entries_for_account(a)
            return entries.balance(date, self._currency)

        return sum(map(bal, self._accounts))

    def _budget_for_date(self, date):
        date_range = DateRange(date.min, date)
        return self.document.budgeted_amount(date_range)

    def compute_data(self):
        accounts = set(a for a in self.document.accounts if a.is_balance_sheet_account())
        self._accounts = accounts - self.document.excluded_accounts
        self._currency = self.document.default_currency
        BalanceGraph.compute_data(self)

    # --- Properties
    @property
    def title(self):
        return tr('Net Worth')

    @property
    def currency(self):
        return self.document.default_currency

