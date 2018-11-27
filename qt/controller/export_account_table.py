# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QHeaderView

from .column import Column
from .table import Table

class ExportAccountTable(Table):
    COLUMNS = [
        Column('name', 80),
        Column('export', 60),
    ]

    def __init__(self, model, view):
        Table.__init__(self, model, view)
        view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        view.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)

    # --- Data methods override
    def _getData(self, row, column, role):
        if column.name == 'export':
            if role == Qt.CheckStateRole:
                return Qt.Checked if row.export else Qt.Unchecked
            else:
                return None
        else:
            return Table._getData(self, row, column, role)

    def _getFlags(self, row, column):
        flags = Table._getFlags(self, row, column)
        if column.name == 'export':
            flags |= Qt.ItemIsUserCheckable | Qt.ItemIsEditable
        return flags

    def _setData(self, row, column, value, role):
        if column.name == 'export':
            if role == Qt.CheckStateRole:
                row.export = value
                return True
            else:
                return False
        else:
            return Table._setData(self, row, column, value, role)

