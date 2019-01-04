# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import trget
from .column import Column
from .table import GUITable, Row, RowWithDebitAndCreditMixIn

trcol = trget('columns')

class SplitTable(GUITable):
    COLUMNS = [
        Column('account', display=trcol("Account")),
        Column('memo', display=trcol("Memo")),
        Column('debit', display=trcol("Debit")),
        Column('credit', display=trcol("Credit")),
    ]

    def __init__(self, transaction_panel):
        GUITable.__init__(self, document=transaction_panel.mainwindow.document)
        self.panel = transaction_panel
        self.completable_edit = self.panel.completable_edit

    # --- Override
    def _do_add(self):
        split = self.panel.new_split()
        row = SplitTableRow(self, split)
        return row, len(self)

    def _do_delete(self):
        self.panel.delete_split(self.selected_row.split)
        self.refresh()

    def _is_edited_new(self):
        split = self.edited.split
        return split not in self.panel.transaction.splits

    def _fill(self):
        transaction = self.panel.transaction
        splits = transaction.splits
        for split in splits:
            self.append(SplitTableRow(self, split))

    def _update_selection(self):
        self.panel.select_splits([row.split for row in self.selected_rows])

    # --- Public
    def move_split(self, from_index, to_index):
        transaction = self.panel.transaction
        row = self[from_index]
        transaction.move_split(row.split, to_index)
        self.refresh(refresh_view=False)
        self.select([to_index])
        self.view.refresh()

    def refresh_splits(self):
        self.refresh_and_show_selection()

    def refresh_initial(self):
        # the refresh just after a panel loading is a bit different
        self.refresh(refresh_view=False)
        self.select([0])
        self.view.refresh()


class SplitTableRow(Row, RowWithDebitAndCreditMixIn):
    def __init__(self, table, split):
        Row.__init__(self, table)
        self.split = split
        self.load()

    def _parse_amount(self, value):
        transaction = self.table.panel.transaction
        if transaction.amount:
            currency = transaction.amount.currency_code
        else:
            currency = self.table.document.default_currency
        return self.table.document.parse_amount(value, default_currency=currency)

    def load(self):
        self._account = self.split.account.name if self.split.account else ''
        self._memo = self.split.memo
        self._amount = self.split.amount

    def save(self):
        self.table.panel.change_split(self.split, self.account, self._amount, self._memo)

    @property
    def account(self):
        return self._account

    @account.setter
    def account(self, value):
        self._edit()
        self._account = value

    @property
    def memo(self):
        return self._memo

    @memo.setter
    def memo(self, value):
        self._edit()
        self._memo = value

    @property
    def credit(self):
        return self.table.document.format_amount(self._credit, blank_zero=True)

    @credit.setter
    def credit(self, value):
        try:
            self._credit = self._parse_amount(value)
        except ValueError:
            pass

    @property
    def debit(self):
        return self.table.document.format_amount(self._debit, blank_zero=True)

    @debit.setter
    def debit(self, value):
        try:
            self._debit = self._parse_amount(value)
        except ValueError:
            pass

