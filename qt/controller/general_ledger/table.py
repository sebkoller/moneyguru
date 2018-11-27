# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QBrush, QColor

from ...const import EXTRA_ROLE, EXTRA_SPAN_ALL_COLUMNS
from ..column import Column
from ..table import DATE_EDIT, DESCRIPTION_EDIT, PAYEE_EDIT, ACCOUNT_EDIT
from ..table_with_transactions import TableWithTransactions

class GeneralLedgerTable(TableWithTransactions):
    COLUMNS = [
        Column('status', 25, cantTruncate=True),
        Column('date', 86, editor=DATE_EDIT, cantTruncate=True),
        Column('reconciliation_date', 110, editor=DATE_EDIT, cantTruncate=True),
        Column('description', 150, editor=DESCRIPTION_EDIT),
        Column('payee', 150, editor=PAYEE_EDIT),
        Column('checkno', 100),
        Column('transfer', 120, editor=ACCOUNT_EDIT),
        Column('debit', 95, alignment=Qt.AlignRight, cantTruncate=True),
        Column('credit', 95, alignment=Qt.AlignRight, cantTruncate=True),
        Column('balance', 110, alignment=Qt.AlignRight, cantTruncate=True),
    ]

    def __init__(self, model, view):
        TableWithTransactions.__init__(self, model, view)
        self.view.deletePressed.connect(self.model.delete)

    # --- Override
    def _getData(self, row, column, role):
        is_account_row = self.model.is_account_row(row)
        if role == EXTRA_ROLE:
            flags = 0
            if is_account_row:
                flags |= EXTRA_SPAN_ALL_COLUMNS
            return flags
        elif is_account_row:
            if role == Qt.DisplayRole:
                return row.account_name
            elif role == Qt.FontRole:
                font = QFont(self.view.font())
                font.setBold(True)
                return font
            elif role == Qt.BackgroundRole:
                return QBrush(QColor(Qt.lightGray))
        elif role == Qt.FontRole:
            font = QFont(self.view.font())
            is_bold = self.model.is_bold_row(row)
            font.setBold(is_bold)
            return font
        else:
            return TableWithTransactions._getData(self, row, column, role)

    def reset(self):
        TableWithTransactions.reset(self)
        self.view.clearSpans()
        for index, row in enumerate(self.model):
            if self.model.is_account_row(row):
                self.view.setSpan(index, 0, 1, len(self.COLUMNS))

