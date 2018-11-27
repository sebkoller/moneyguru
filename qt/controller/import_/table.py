# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QMimeData, QByteArray
from PyQt5.QtGui import QPixmap

from ..column import Column
from ..table import Table, NO_EDIT

MIME_INDEXES = 'application/moneyguru.rowindexes'

class ImportTable(Table):
    COLUMNS = [
        Column('will_import', 20, editor=NO_EDIT),
        Column('date', 80),
        Column('description', 90),
        Column('amount', 90, alignment=Qt.AlignRight),
        Column('bound', 22),
        Column('date_import', 80),
        Column('description_import', 90),
        Column('payee_import', 90),
        Column('checkno_import', 57),
        Column('transfer_import', 90),
        Column('amount_import', 90, alignment=Qt.AlignRight),
    ]

    def __init__(self, model, view):
        Table.__init__(self, model, view)
        self.view.clicked.connect(self.cellClicked)
        self.view.spacePressed.connect(self.spacePressed)

    # --- Data methods override
    def _getData(self, row, column, role):
        if column.name == 'will_import':
            if role == Qt.CheckStateRole:
                return Qt.Checked if row.will_import else Qt.Unchecked
            else:
                return None
        elif column.name == 'bound':
            if role == Qt.DecorationRole:
                return QPixmap(':/lock_12') if row.bound else None
            else:
                return None
        else:
            return Table._getData(self, row, column, role)

    def _getFlags(self, row, column):
        flags = Table._getFlags(self, row, column)
        if column.name == 'will_import':
            flags |= Qt.ItemIsUserCheckable | Qt.ItemIsEditable
            if not row.can_edit_will_import:
                flags &= ~Qt.ItemIsEnabled
        if not row.bound:
            flags |= Qt.ItemIsDragEnabled | Qt.ItemIsDropEnabled
        return flags

    def _setData(self, row, column, value, role):
        if column.name == 'will_import':
            if role == Qt.CheckStateRole:
                row.will_import = value
                return True
            else:
                return False
        else:
            return Table._setData(self, row, column, value, role)

    # --- Drag & Drop
    def dropMimeData(self, mimeData, action, row, column, parentIndex):
        if not mimeData.hasFormat(MIME_INDEXES):
            return False
        if not parentIndex.isValid():
            return False
        strMimeData = bytes(mimeData.data(MIME_INDEXES)).decode()
        indexes = list(map(int, strMimeData.split(',')))
        if len(indexes) != 1:
            return False
        index = indexes[0]
        if not self.model.can_bind(index, parentIndex.row()):
            return False
        # If we dont do the layoutChanged thing, we get a weird situation where the row below the
        # the dragged row has its will_import unchecked.
        self.layoutAboutToBeChanged.emit()
        self.model.bind(index, parentIndex.row())
        self.layoutChanged.emit()
        return True

    def mimeData(self, indexes):
        rows = set(str(index.row()) for index in indexes)
        data = ','.join(rows)
        mimeData = QMimeData()
        mimeData.setData(MIME_INDEXES, QByteArray(data.encode()))
        return mimeData

    def mimeTypes(self):
        return [MIME_INDEXES]

    def supportedDropActions(self):
        return Qt.MoveAction

    # --- Private
    def _switchToOneSidedMode(self):
        h = self.view.horizontalHeader()
        if h.isSectionHidden(1):
            return # already in one sided mode
        for i in [1, 2, 3, 4]:
            h.hideSection(i)

    def _switchToTwoSidedMode(self):
        h = self.view.horizontalHeader()
        if not h.isSectionHidden(1):
            return # already in two sided mode
        for i in [1, 2, 3, 4]:
            h.showSection(i)

    # --- Public
    def updateColumnsVisibility(self):
        if self.model.is_two_sided:
            self._switchToTwoSidedMode()
        else:
            self._switchToOneSidedMode()

    # --- Event Handling
    def cellClicked(self, index):
        column = self.model.columns.column_by_index(index.column())
        rowattr = column.name
        if rowattr == 'bound':
            self.model.unbind(index.row())

    def spacePressed(self):
        selectedIndexes = self.view.selectionModel().selectedRows()
        for index in selectedIndexes:
            row = self.model[index.row()]
            row.will_import = not row.will_import
        self.refresh()

