# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr, trget
from core.util import dedupe
from .column import Column, Columns
from .entry_table_base import EntryTableBase, PreviousBalanceRow, TotalRow

trcol = trget('columns')

class EntryTableColumns(Columns):
    def _set_debit_credit_mode(self, active):
        self.set_column_visible('debit', active)
        self.set_column_visible('credit', active)
        self.set_column_visible('increase', not active)
        self.set_column_visible('decrease', not active)

    def menu_items(self):
        items = Columns.menu_items(self)
        marked = self.column_is_visible('debit')
        items.append((tr("Debit/Credit"), marked))
        return items

    def toggle_menu_item(self, index):
        if index == len(self._optional_columns()):
            debit_visible = self.column_is_visible('debit')
            self._set_debit_credit_mode(not debit_visible)
        else:
            Columns.toggle_menu_item(self, index)

    def save_columns(self):
        Columns.save_columns(self)
        pref_name = '{}.Columns.debit_credit_mode'.format(self.savename)
        value = self.column_is_visible('debit')
        self.prefaccess.set_default(pref_name, value)

    def restore_columns(self):
        Columns.restore_columns(self)
        pref_name = '{}.Columns.debit_credit_mode'.format(self.savename)
        debit_credit_mode = bool(self.prefaccess.get_default(pref_name))
        self._set_debit_credit_mode(debit_credit_mode)


class EntryTable(EntryTableBase):
    SAVENAME = 'EntryTable'
    COLUMNS = [
        Column('status', display=''),
        Column('date', display=trcol("Date")),
        Column('reconciliation_date', display=trcol("Reconciliation Date"), visible=False, optional=True),
        Column('checkno', display=trcol("Check #"), visible=False, optional=True),
        Column('description', display=trcol("Description"), optional=True),
        Column('payee', display=trcol("Payee"), visible=False, optional=True),
        Column('transfer', display=trcol("Transfer")),
        Column('increase', display=trcol("Increase")),
        Column('decrease', display=trcol("Decrease")),
        Column('debit', display=trcol("Debit"), visible=False),
        Column('credit', display=trcol("Credit"), visible=False),
        Column('balance', display=trcol("Balance")),
    ]

    def __init__(self, account_view):
        EntryTableBase.__init__(self, account_view)
        self.columns = EntryTableColumns(self, prefaccess=account_view.document, savename=self.SAVENAME)
        self.account = account_view.account
        self.completable_edit.account = self.account
        self._reconciliation_mode = False

    # --- Override
    def _fill(self):
        account = self.account
        if account is None:
            return
        self.account = account
        rows = self._get_account_rows(account)
        is_native = lambda row: self.document.is_amount_native(row._debit)\
            and self.document.is_amount_native(row._credit)
        self._all_amounts_are_native = all(is_native(row) for row in rows)
        if not rows:
            # We still show a total row
            rows.append(TotalRow(self, account, self.document.date_range.end, 0, 0))
        if isinstance(rows[0], PreviousBalanceRow):
            self.header = rows[0]
            del rows[0]
        for row in rows[:-1]:
            self.append(row)
        self.footer = rows[-1]
        balance_visible = account.is_balance_sheet_account()
        self.columns.set_column_visible('balance', balance_visible)
        self._restore_from_explicit_selection(refresh_view=False)

    def _get_current_account(self):
        return self.account

    def _get_totals_currency(self):
        return self._get_current_account().currency

    def _revalidate(self, prev_date_range=None):
        if prev_date_range:
            transactions = self.selected_transactions
            date = transactions[0].date if transactions else prev_date_range.end
            delta_before_change = date - prev_date_range.start
            date_range = self.document.date_range
        EntryTableBase._revalidate(self)
        self.refresh(refresh_view=False)
        self.select_transactions(self.mainwindow.selected_transactions)
        if prev_date_range and not self.selected_indexes:
            self._select_nearest_date(date_range.start + delta_before_change)
        self.view.refresh()
        self.view.show_selected_row()
        self.mainwindow.selected_transactions = self.selected_transactions

    # --- Public
    def show_transfer_account(self, row_index=None):
        if row_index is None:
            if not self.selected_entries:
                return
            row_index = self.selected_index
        entry = self[row_index].entry
        splits = entry.transaction.splits
        accounts = dedupe(split.account for split in splits if split.account is not None)
        if len(accounts) < 2:
            return # no transfer
        index = accounts.index(entry.account)
        if index < len(accounts) - 1:
            account_to_show = accounts[index+1]
        else:
            account_to_show = accounts[0]
        self.mainwindow.open_account(account_to_show)

    def toggle_reconciled(self):
        """Toggle the reconcile flag of selected entries"""
        entries = [row.entry for row in self.selected_rows if row.can_reconcile()]
        self.document.toggle_entries_reconciled(entries)
        self.mainwindow.revalidate()

    # --- Properties
    @property
    def reconciliation_mode(self):
        return self._reconciliation_mode

    @reconciliation_mode.setter
    def reconciliation_mode(self, value):
        if value == self._reconciliation_mode:
            return
        self._reconciliation_mode = value
        self.refresh()
