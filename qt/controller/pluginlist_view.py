# Copyright 2016 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtWidgets import QVBoxLayout, QLabel, QAbstractItemView

from core.trans import trget

from ..support.item_view import TableView
from .base_view import BaseView
from .pluginlist_table import PluginListTable

tr = trget('ui')

class PluginListView(BaseView):
    def _setup(self):
        self._setupUi()
        self.table = PluginListTable(model=self.model.table, view=self.tableView)
        self._setupColumns() # Can only be done after the model has been connected

    def _setupUi(self):
        self.mainLayout = QVBoxLayout(self)
        text = tr("moneyGuru has to be restarted for plugin changes to take effect.")
        self.mainLayout.addWidget(QLabel(text))
        self.tableView = TableView(self)
        self.tableView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.horizontalHeader().setHighlightSections(False)
        self.tableView.horizontalHeader().setMinimumSectionSize(18)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.verticalHeader().setDefaultSectionSize(18)
        self.mainLayout.addWidget(self.tableView)

    def _setupColumns(self):
        h = self.tableView.horizontalHeader()
        h.setSectionsMovable(True) # column drag & drop reorder


