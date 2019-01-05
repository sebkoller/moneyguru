# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .bar_graph import BarGraph

class AccountFlowGraph(BarGraph):
    def __init__(self, account_view):
        BarGraph.__init__(self, account_view)
        self._account = account_view.account

    # --- Override
    def _currency(self):
        return self._account.currency

    def _get_cash_flow(self, date_range):
        self.document.oven.continue_cooking(date_range.end) # it's possible that the overflow is not cooked
        account = self._account
        entries = self.document.accounts.entries_for_account(account)
        currency = self._currency()
        cash_flow = entries.normal_cash_flow(date_range, currency)
        budgeted = self.document.budgets.normal_amount_for_account(account, date_range, currency)
        return cash_flow + budgeted

    # --- Properties
    @property
    def title(self):
        return self._account.name

