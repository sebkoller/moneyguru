# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import (
    Qt, QAbstractTableModel, QModelIndex, QItemSelectionModel, QItemSelection)
from PyQt5.QtGui import QFontMetrics

from ..support.completable_edit import DescriptionEdit, PayeeEdit, AccountEdit
from ..support.column_view import AmountPainter
from ..support.date_edit import DateEdit
from ..support.item_delegate import ItemDelegate
from .column import Columns

NO_EDIT = 'no_edit'
DATE_EDIT = 'date_edit'
DESCRIPTION_EDIT = 'description_edit'
PAYEE_EDIT = 'payee_edit'
ACCOUNT_EDIT = 'account_edit'

# See #14, #15 Added to indicate an amount to be painted to a table
# with nicely aligned currency / value
AMOUNT_PAINTER = 'amount_painter'

EDIT_TYPE2COMPLETABLE_EDIT = {
    DESCRIPTION_EDIT: DescriptionEdit,
    PAYEE_EDIT: PayeeEdit,
    ACCOUNT_EDIT: AccountEdit
}

class TableDelegate(ItemDelegate):
    def __init__(self, model):
        ItemDelegate.__init__(self)
        self._model = model
        self._column_painters = {}
        for column in self._model.columns.column_list:
            if column.painter == AMOUNT_PAINTER:
                # See #14, #15.
                self._column_painters[column.name] = AmountPainter(column.name, self._model)

    def _get_value_painter(self, index):
        column = self._model.columns.column_by_index(index.column())

        if column.name in self._column_painters:
            return self._column_painters[column.name]

    def createEditor(self, parent, option, index):
        column = self._model.columns.column_by_index(index.column())
        editType = column.editor
        if editType is None:
            return ItemDelegate.createEditor(self, parent, option, index)
        elif editType == NO_EDIT:
            return None
        elif editType == DATE_EDIT:
            return DateEdit(parent)
        elif editType in EDIT_TYPE2COMPLETABLE_EDIT:
            return EDIT_TYPE2COMPLETABLE_EDIT[editType](self._model.completable_edit, parent)


class TableBase(QAbstractTableModel):
    # Flags you want when index.isValid() is False. In those cases, _getFlags() is never called.
    INVALID_INDEX_FLAGS = Qt.ItemIsEnabled
    COLUMNS = []

    def __init__(self, model, view, **kwargs):
        super().__init__(**kwargs)
        self.model = model
        self.view = view
        self.view.setModel(self)
        self.model.view = self
        if hasattr(self.model, 'columns'):
            self.columns = Columns(self.model.columns, self.COLUMNS, view.horizontalHeader())

        self.view.selectionModel().selectionChanged[(QItemSelection, QItemSelection)].connect(self.selectionChanged)

    def _updateModelSelection(self):
        # Takes the selection on the view's side and update the model with it.
        # an _updateViewSelection() call will normally result in an _updateModelSelection() call.
        # to avoid infinite loops, we check that the selection will actually change before calling
        # model.select()
        newIndexes = [modelIndex.row() for modelIndex in self.view.selectionModel().selectedRows()]
        if newIndexes != self.model.selected_indexes:
            self.model.select(newIndexes)

    def _updateViewSelection(self):
        # Takes the selection on the model's side and update the view with it.
        newSelection = QItemSelection()
        columnCount = self.columnCount(QModelIndex())
        for index in self.model.selected_indexes:
            newSelection.select(self.createIndex(index, 0), self.createIndex(index, columnCount-1))
        self.view.selectionModel().select(newSelection, QItemSelectionModel.ClearAndSelect)
        if len(newSelection.indexes()):
            currentIndex = newSelection.indexes()[0]
            self.view.selectionModel().setCurrentIndex(currentIndex, QItemSelectionModel.Current)
            self.view.scrollTo(currentIndex)

    # --- Data Model methods
    # Virtual
    def _getData(self, row, column, role):
        if role in (Qt.DisplayRole, Qt.EditRole):
            attrname = column.name
            return row.get_cell_value(attrname)
        elif role == Qt.TextAlignmentRole:
            return column.alignment
        return None

    # Virtual
    def _getFlags(self, row, column):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if row.can_edit_cell(column.name):
            flags |= Qt.ItemIsEditable
        return flags

    # Virtual
    def _setData(self, row, column, value, role):
        if role == Qt.EditRole:
            attrname = column.name
            if attrname == 'from':
                attrname = 'from_'
            setattr(row, attrname, value)
            return True
        return False

    def columnCount(self, index):
        return self.model.columns.columns_count()

    def data(self, index, role):
        if not index.isValid():
            return None
        row = self.model[index.row()]
        column = self.model.columns.column_by_index(index.column())
        return self._getData(row, column, role)

    def flags(self, index):
        if not index.isValid():
            return self.INVALID_INDEX_FLAGS
        row = self.model[index.row()]
        column = self.model.columns.column_by_index(index.column())
        return self._getFlags(row, column)

    def headerData(self, section, orientation, role):
        if orientation != Qt.Horizontal:
            return None
        if section >= self.model.columns.columns_count():
            return None
        column = self.model.columns.column_by_index(section)
        if role == Qt.DisplayRole:
            return column.display
        elif role == Qt.TextAlignmentRole:
            return column.alignment
        else:
            return None

    def revert(self):
        self.model.cancel_edits()

    def rowCount(self, index):
        if index.isValid():
            return 0
        return len(self.model)

    def setData(self, index, value, role):
        if not index.isValid():
            return False
        row = self.model[index.row()]
        column = self.model.columns.column_by_index(index.column())
        return self._setData(row, column, value, role)

    def sort(self, section, order):
        column = self.model.columns.column_by_index(section)
        attrname = column.name
        self.model.sort_by(attrname, desc=(order == Qt.DescendingOrder))

    def submit(self):
        self.model.save_edits()
        return True

    # --- Events
    def selectionChanged(self, selected, deselected):
        self._updateModelSelection()

    # --- model --> view
    def refresh(self):
        self.beginResetModel()
        self.endResetModel()
        self._updateViewSelection()

    def show_selected_row(self):
        if self.model.selected_index is not None:
            self.view.showRow(self.model.selected_index)

    def start_editing(self):
        self.view.editSelected()

    def stop_editing(self):
        self.view.setFocus() # enough to stop editing

    def update_selection(self):
        self._updateViewSelection()


class Table(TableBase):
    def __init__(self, model, view):
        TableBase.__init__(self, model, view)
        self._selectionUpdateOverrideFlag = False
        self.tableDelegate = TableDelegate(self.model)
        self.view.setItemDelegate(self.tableDelegate)
        from ..app import APP_PREFS
        self._updateFontSize(prefs=APP_PREFS)
        APP_PREFS.prefsChanged.connect(self.appPrefsChanged)

    def _overrideNextSelectionUpdate(self):
        """Cancel the next selection update coming from Qt.

        This is a hackish way to go around a mild annoyance: click-induced selection clearing. By
        default, when clicking on a checkbox in a table, Qt *clears* the selection afterwards,
        which leaves us without selection at all. It's not very user-friendly for our needs, so we
        go around it.

        By calling this method, you set a flag and the next time that a selection update trying to
        make its way to the model arrives, it's shorted. This happens only once.
        """
        self._selectionUpdateOverrideFlag = True

    def _updateModelSelection(self):
        if self._selectionUpdateOverrideFlag:
            self._selectionUpdateOverrideFlag = False
            # We still probably need, however, to refresh the model's selection on the Qt side.
            self._updateViewSelection()
        else:
            TableBase._updateModelSelection(self)

    def _updateFontSize(self, prefs):
        font = self.view.font()
        font.setPointSize(prefs.tableFontSize)
        self.view.setFont(font)
        fm = QFontMetrics(font)
        self.view.verticalHeader().setDefaultSectionSize(fm.height()+2)
        # (#14, #15) When a new font was selected in the preferences panel,
        # the column would redraw but not resize appropriately.  A call
        # to resize(sizeHint()) was added on the update of the size info
        # in the custom drawing for the amount field.
        self.view.resize(self.view.sizeHint())

    def appPrefsChanged(self):
        self._updateFontSize(prefs=self.sender())

