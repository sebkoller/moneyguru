# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..model.date import DateRange
from .balance_graph import BalanceGraph

class AccountBalanceGraph(BalanceGraph):
    def __init__(self, account_view):
        BalanceGraph.__init__(self, account_view)
        self._account = account_view.account

    def _balance_for_date(self, date):
        if self._account is None:
            return 0
        entries = self.document.accounts.entries_for_account(self._account)
        entry = entries.last_entry(date)
        return entry.normal_balance() if entry else 0

    def _budget_for_date(self, date):
        date_range = DateRange(date.min, date)
        return self.document.budgeted_amount_for_target(
            self._account, date_range, filter_excluded=False
        )

    # --- Properties
    @property
    def title(self):
        return self._account.name

    @property
    def currency(self):
        return self._account.currency

