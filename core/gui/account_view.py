# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr
from ..const import PaneType
from .filter_bar import EntryFilterBar
from .entry_table import EntryTable
from .account_balance_graph import AccountBalanceGraph
from .account_flow_graph import AccountFlowGraph
from .transaction_print import EntryPrint
from .transaction_view import TransactionViewBase

class AccountView(TransactionViewBase):
    VIEW_TYPE = PaneType.Account
    PRINT_TITLE_FORMAT = tr('{account_name}\nEntries from {start_date} to {end_date}')
    PRINT_VIEW_CLASS = EntryPrint

    def __init__(self, mainwindow, account):
        TransactionViewBase.__init__(self, mainwindow)
        assert account is not None
        self.account = account
        self._reconciliation_mode = False
        self.etable = self.table = EntryTable(self)
        self.maintable = self.etable
        self.columns = self.maintable.columns
        self.balgraph = AccountBalanceGraph(self)
        self.bargraph = AccountFlowGraph(self)
        self.filter_bar = EntryFilterBar(self)
        if account.is_balance_sheet_account():
            self._shown_graph = self.balgraph
        else:
            self._shown_graph = self.bargraph
        self.restore_subviews_size()

    # --- Override
    def _view_updated(self):
        if self._shown_graph is self.balgraph:
            self.view.show_line_graph()
        else:
            self.view.show_bar_graph()

    def _revalidate(self):
        TransactionViewBase._revalidate(self)
        self.filter_bar.refresh()

    def _refresh_totals(self):
        # _shown_graph is not precisely a "total", but whenever we want to
        # refresh totals, we'll want to refresh the graph as well.
        self._shown_graph._revalidate()
        account = self.account
        if account is None:
            return
        selected, total, total_debit, total_credit = self.etable.get_totals()
        if account.is_debit_account():
            increase = total_debit
            decrease = total_credit
        else:
            increase = total_credit
            decrease = total_debit
        total_increase_fmt = self.document.format_amount(increase)
        total_decrease_fmt = self.document.format_amount(decrease)
        msg = tr("{0} out of {1} selected. Increase: {2} Decrease: {3}")
        self.status_line = msg.format(selected, total, total_increase_fmt, total_decrease_fmt)

    def apply_date_range(self, new_date_range, prev_date_range):
        self._invalidate_cache()
        self.table._revalidate(prev_date_range=prev_date_range)
        self._refresh_totals()

    def restore_subviews_size(self):
        if self.balgraph.view_size[1]:
            # Was already restored
            return
        self.graph_height_to_restore = self.document.get_default('AccountView.GraphHeight', 0)

    def show(self):
        self.etable.columns.restore_columns()
        TransactionViewBase.show(self)
        self.etable.show()
        self._refresh_totals()
        self.view.refresh_reconciliation_button()
        self.filter_bar.refresh()
        self.view.update_visibility()

    def hide(self):
        self.etable.columns.save_columns()
        TransactionViewBase.hide(self)

    def save_preferences(self):
        # Unlike other views, we don't save preferences on pane closing, but much more frequently:
        # on pane swapping. We do this because AccountView columns are shared between multiple
        # instances and changing a column in a pane should result in the same change being done
        # in other tabs. That's why we save/restore in hide()/show().
        # ... Except for graph size. We don't keep separate graph size prefs for each account.
        height = self._shown_graph.view_size[1]
        # It's possible that set_view_size() has never been called. In this case, we have (0, 0).
        if height:
            self.document.set_default('AccountView.GraphHeight', height)

    def update_transaction_selection(self, transactions):
        self._refresh_totals()

    def update_visibility(self):
        self.view.update_visibility()

    # --- Public
    def navigate_back(self):
        """When the entry table is shown, go back to the appropriate report."""
        if self.account.is_balance_sheet_account():
            self.mainwindow.select_pane_of_type(PaneType.NetWorth)
        else:
            self.mainwindow.select_pane_of_type(PaneType.Profit)

    def move_down(self):
        self.etable.move_down()

    def move_up(self):
        self.etable.move_up()

    def show_account(self):
        self.etable.show_transfer_account()

    def toggle_reconciliation_mode(self):
        self._reconciliation_mode = not self._reconciliation_mode
        self.etable.reconciliation_mode = self._reconciliation_mode
        self.view.refresh_reconciliation_button()

    # --- Properties
    @property
    def can_toggle_reconciliation_mode(self):
        return self.account.is_balance_sheet_account()

    @property
    def reconciliation_mode(self):
        return self._reconciliation_mode
