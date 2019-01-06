# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from core.trans import tr
from ..const import PaneType, FilterType
from ..model.account import AccountType
from ..model.amount import convert_amount
from ..model.transaction import txn_matches
from .base import BaseView
from .filter_bar import FilterBar
from .mass_edition_panel import MassEditionPanel
from .transaction_table import TransactionTable
from .transaction_print import TransactionPrint
from .transaction_panel import TransactionPanel


class TransactionViewBase(BaseView):
    def edit_selected_transactions(self):
        editable_txns = [txn for txn in self.mainwindow.selected_transactions if not txn.is_budget]
        if len(editable_txns) > 1:
            panel = MassEditionPanel(self.mainwindow)
            panel.view = weakref.proxy(self.view.get_panel_view(panel))
            panel.load(editable_txns)
            return panel
        elif len(editable_txns) == 1:
            panel = TransactionPanel(self.mainwindow)
            panel.view = weakref.proxy(self.view.get_panel_view(panel))
            panel.load(editable_txns[0])
            return panel

    # --- Virtuals
    def _invalidate_cache(self):
        pass

    def _refresh_totals(self):
        pass

    # --- Overrides
    def _revalidate(self):
        self._invalidate_cache()
        self.table.refresh_and_show_selection()
        self._refresh_totals()

    def apply_date_range(self, new_date_range, prev_date_range):
        self._revalidate()

    def apply_filter(self):
        self._revalidate()

    def restore_view(self):
        super().restore_view()
        self.table.restore_view()

    # --- Public
    def delete_item(self):
        self.table.delete()

    def duplicate_item(self):
        self.table.duplicate_selected()

    def edit_item(self):
        return self.edit_selected_transactions()

    def new_item(self):
        self.table.add()

    def stop_editing(self):
        self.table.cancel_edits()


class TransactionView(TransactionViewBase):
    VIEW_TYPE = PaneType.Transaction
    PRINT_TITLE_FORMAT = tr('Transactions from {start_date} to {end_date}')
    PRINT_VIEW_CLASS = TransactionPrint

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self._visible_transactions = None
        self.filter_bar = FilterBar(self)
        self.ttable = self.table = TransactionTable(self)
        self.maintable = self.ttable
        self.columns = self.maintable.columns
        self.restore_subviews_size()

    def _revalidate(self):
        TransactionViewBase._revalidate(self)
        self.filter_bar.refresh()

    # --- Private
    def _refresh_totals(self):
        selected = len(self.mainwindow.selected_transactions)
        total = len(self.visible_transactions)
        currency = self.document.default_currency
        total_amount = sum(convert_amount(t.amount, currency, t.date) for t in self.mainwindow.selected_transactions)
        total_amount_fmt = self.document.format_amount(total_amount)
        msg = tr("{0} out of {1} selected. Amount: {2}")
        self.status_line = msg.format(selected, total, total_amount_fmt)

    def _set_visible_transactions(self):
        date_range = self.document.date_range
        txns = [t for t in self.document.oven.transactions if t.date in date_range]
        query_string = self.mainwindow.filter_string
        filter_type = self.mainwindow.filter_type
        if not query_string and filter_type is None:
            self._visible_transactions = txns
            return
        if query_string:
            query = self.app.parse_search_query(query_string)
            txns = [t for t in txns if txn_matches(t, query)]
        if filter_type is FilterType.Unassigned:
            txns = [t for t in txns if t.has_unassigned_split]
        elif filter_type is FilterType.Income:
            txns = [t for t in txns if any(getattr(s.account, 'type', '') == AccountType.Income for s in t.splits)]
        elif filter_type is FilterType.Expense:
            txns = [t for t in txns if any(getattr(s.account, 'type', '') == AccountType.Expense for s in t.splits)]
        elif filter_type is FilterType.Transfer:
            def is_transfer(t):
                return len([s for s in t.splits if s.account is not None and s.account.is_balance_sheet_account()]) >= 2
            txns = list(filter(is_transfer, txns))
        elif filter_type is FilterType.Reconciled:
            txns = [t for t in txns if any(s.reconciled for s in t.splits)]
        elif filter_type is FilterType.NotReconciled:
            txns = [t for t in txns if all(not s.reconciled for s in t.splits)]
        self._visible_transactions = txns

    # --- Override
    def _invalidate_cache(self):
        self._visible_transactions = None

    def save_preferences(self):
        self.ttable.columns.save_columns()

    def show(self):
        super().show()
        self.ttable.show()

    def update_transaction_selection(self, transactions):
        self._refresh_totals()

    # --- Public
    def move_down(self):
        self.ttable.move_down()

    def move_up(self):
        self.ttable.move_up()

    def show_account(self):
        self.ttable.show_from_account()

    # --- Properties
    @property
    def visible_transactions(self):
        if self._visible_transactions is None:
            self._set_visible_transactions()
        return self._visible_transactions
