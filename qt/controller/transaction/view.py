# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5 import QtCore
from PyQt5.QtWidgets import (
    QVBoxLayout, QSizePolicy, QAbstractItemView
)


from ...support.item_view import TableView
from ...support.radio_box import RadioBox
from ..base_transaction_view import BaseTransactionView
from .filter_bar import TransactionFilterBar
from .table import TransactionTable

class TransactionView(BaseTransactionView):
    def _setup(self):
        self._setupUi()
        self.ttable = TransactionTable(self.model.ttable, view=self.tableView)
        self.tfbar = TransactionFilterBar(model=self.model.filter_bar, view=self.filterBar)
        self._setupColumns() # Can only be done after the model has been connected

    def _setupUi(self):
        self.resize(400, 300)
        self.verticalLayout = QVBoxLayout(self)
        self.verticalLayout.setSpacing(0)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        self.filterBar = RadioBox(self)
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.filterBar.sizePolicy().hasHeightForWidth())
        self.filterBar.setSizePolicy(sizePolicy)
        self.filterBar.setMinimumSize(QtCore.QSize(0, 20))
        self.verticalLayout.addWidget(self.filterBar)
        self.tableView = TableView(self)
        self.tableView.setAcceptDrops(True)
        self.tableView.setEditTriggers(QAbstractItemView.DoubleClicked|QAbstractItemView.EditKeyPressed)
        self.tableView.setDragEnabled(True)
        self.tableView.setDragDropMode(QAbstractItemView.InternalMove)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.setSortingEnabled(True)
        self.tableView.setCornerButtonEnabled(False)
        self.tableView.horizontalHeader().setHighlightSections(False)
        self.tableView.horizontalHeader().setMinimumSectionSize(18)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.verticalHeader().setDefaultSectionSize(18)
        self.verticalLayout.addWidget(self.tableView)

    def _setupColumns(self):
        h = self.tableView.horizontalHeader()
        h.setSectionsMovable(True) # column drag & drop reorder

    # --- QWidget override
    def setFocus(self):
        self.ttable.view.setFocus()

    # --- Public
    def fitViewsForPrint(self, viewPrinter):
        viewPrinter.fitTable(self.ttable)

