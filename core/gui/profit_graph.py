# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr

from .bar_graph import BarGraph

class ProfitGraph(BarGraph):
    def __init__(self, profit_view):
        BarGraph.__init__(self, profit_view)

    # --- Override
    def _currency(self):
        return self.document.default_currency

    def _get_cash_flow(self, date_range):
        self.document.oven.continue_cooking(date_range.end) # it's possible that the overflow is not cooked
        accounts = {a for a in self.document.accounts if a.is_income_statement_account()}
        accounts = accounts - self.document.excluded_accounts

        def getentries(a):
            return self.document.accounts.entries_for_account(a)

        cash_flow = -sum(
            getentries(a).cash_flow(date_range, self.document.default_currency)
            for a in accounts)
        budgeted_amount = self.document.budgeted_amount(date_range)
        return cash_flow + budgeted_amount

    def _is_reverted(self):
        return True

    # --- Properties
    @property
    def title(self):
        return tr('Profit & Loss')

