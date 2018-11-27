# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

from ...support.item_delegate import ItemDecoration
from ..column import Column
from ..table import TableDelegate, DATE_EDIT, DESCRIPTION_EDIT, PAYEE_EDIT, ACCOUNT_EDIT, AMOUNT_PAINTER
from ..table_with_transactions import TableWithTransactions

class EntryTableDelegate(TableDelegate):
    def __init__(self, model):
        TableDelegate.__init__(self, model)
        arrow = QPixmap(':/right_arrow_gray_12')
        arrowSelected = QPixmap(':/right_arrow_white_12')
        self._decoArrow = ItemDecoration(arrow, self.show_transfer_account)
        self._decoArrowSelected = ItemDecoration(arrowSelected, self.show_transfer_account)

    def show_transfer_account(self, index):
        self._model.show_transfer_account(row_index=index.row())

    def _get_decorations(self, index, isSelected):
        column = self._model.columns.column_by_index(index.column())
        if column.name == 'transfer':
            return [self._decoArrowSelected if isSelected else self._decoArrow]
        else:
            return []


class EntryTable(TableWithTransactions):
    COLUMNS = [
        Column('status', 25, cantTruncate=True),
        Column('date', 86, editor=DATE_EDIT, cantTruncate=True),
        Column('reconciliation_date', 110, editor=DATE_EDIT, cantTruncate=True),
        Column('description', 150, editor=DESCRIPTION_EDIT),
        Column('payee', 150, editor=PAYEE_EDIT),
        Column('checkno', 100),
        Column('transfer', 120, editor=ACCOUNT_EDIT),
        Column('increase', 95, alignment=Qt.AlignRight, cantTruncate=True, painter=AMOUNT_PAINTER, resizeToFit=True),
        Column('decrease', 95, alignment=Qt.AlignRight, cantTruncate=True, painter=AMOUNT_PAINTER, resizeToFit=True),
        Column('debit', 95, alignment=Qt.AlignRight, cantTruncate=True),
        Column('credit', 95, alignment=Qt.AlignRight, cantTruncate=True),
        Column('balance', 110, alignment=Qt.AlignRight, cantTruncate=True),
    ]

    def __init__(self, model, view):
        TableWithTransactions.__init__(self, model, view)
        self.tableDelegate = EntryTableDelegate(self.model)
        self.view.setItemDelegate(self.tableDelegate)
        self.view.sortByColumn(1, Qt.AscendingOrder) # sorted by date by default
        self.view.spacePressed.connect(self.model.toggle_reconciled)
        self.view.deletePressed.connect(self.model.delete)

    # --- Data methods override
    def _getStatusData(self, row, role):
        # DecorationRole is handled in TableWithTransactions
        if role == Qt.CheckStateRole:
            if row.can_reconcile():
                return Qt.Checked if row.reconciled else Qt.Unchecked
            else:
                return None
        else:
            return TableWithTransactions._getStatusData(self, row, role)

    def _getFlags(self, row, column):
        flags = TableWithTransactions._getFlags(self, row, column)
        if column.name == 'status':
            if row.can_reconcile():
                flags |= Qt.ItemIsUserCheckable
        return flags

    def _setData(self, row, column, value, role):
        if column.name == 'status':
            if role == Qt.CheckStateRole:
                row.toggle_reconciled()
                self._overrideNextSelectionUpdate()
                return True
            else:
                return False
        else:
            return TableWithTransactions._setData(self, row, column, value, role)


