# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt

from .column import Column
from .table import Table

class PluginListTable(Table):
    COLUMNS = [
        Column('enabled', 60),
        Column('name', 300),
        Column('type', 150),
        Column('author', 120),
    ]

    # --- Override
    def _getData(self, row, column, role):
        if column.name == 'enabled':
            if role == Qt.CheckStateRole:
                return Qt.Checked if row.enabled else Qt.Unchecked
            else:
                return None
        else:
            return Table._getData(self, row, column, role)

    def _getFlags(self, row, column):
        flags = Table._getFlags(self, row, column)
        if column.name == 'enabled':
            flags |= Qt.ItemIsUserCheckable
        return flags

    def _setData(self, row, column, value, role):
        if column.name == 'enabled':
            if role == Qt.CheckStateRole:
                row.enabled = not row.enabled
                return True
            else:
                return False
        else:
            return Table._setData(self, row, column, value, role)


