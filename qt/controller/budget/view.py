# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QAbstractItemView, QComboBox, QLabel, QSpinBox)

from core.trans import trget

from ...support.date_edit import DateEdit
from ...support.item_view import TableView
from ...util import horizontalSpacer
from ..base_view import BaseView
from ..budget_panel import BudgetPanel
from ..selectable_list import ComboboxModel
from .table import BudgetTable

tr = trget('ui')

class BudgetView(BaseView):
    def _setup(self):
        self._setupUi()
        self.repeatTypeComboBox = ComboboxModel(
            model=self.model.repeat_type_list, view=self.repeatTypeComboBoxView)
        self.btable = BudgetTable(model=self.model.table, view=self.tableView)
        self._setupColumns() # Can only be done after the model has been connected
        self.startDateEdit.editingFinished.connect(self.startDateEditChanged)
        self.repeatEverySpinBox.valueChanged.connect(self.repeatEverySpinBoxChanged)

    def _setupUi(self):
        self.resize(400, 300)
        self.verticalLayout = QVBoxLayout(self)
        self.verticalLayout.setContentsMargins(0, 0, 0, 0)
        topLayout = QHBoxLayout()
        label = QLabel(tr("Start Date:"))
        topLayout.addWidget(label)
        self.startDateEdit = DateEdit(self)
        self.startDateEdit.setMaximumWidth(120)
        label.setBuddy(self.startDateEdit)
        topLayout.addWidget(self.startDateEdit)
        label = QLabel(tr("Repeat Type:"))
        topLayout.addWidget(label)
        self.repeatTypeComboBoxView = QComboBox(self)
        label.setBuddy(self.repeatTypeComboBoxView)
        topLayout.addWidget(self.repeatTypeComboBoxView)
        label = QLabel(tr("Every:"))
        topLayout.addWidget(label)
        self.repeatEverySpinBox = QSpinBox(self)
        self.repeatEverySpinBox.setMinimum(1)
        label.setBuddy(self.repeatEverySpinBox)
        topLayout.addWidget(self.repeatEverySpinBox)
        self.repeatEveryDescLabel = QLabel(self)
        topLayout.addWidget(self.repeatEveryDescLabel)
        topLayout.addItem(horizontalSpacer())
        self.verticalLayout.addLayout(topLayout)
        self.tableView = TableView(self)
        self.tableView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.setSortingEnabled(True)
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
        self.btable.view.setFocus()

    # --- Public
    def fitViewsForPrint(self, viewPrinter):
        viewPrinter.fitTable(self.btable)

    # --- Event Handlers
    def startDateEditChanged(self):
        self.model.start_date = self.sender().text()

    def repeatEverySpinBoxChanged(self):
        self.model.repeat_every = self.sender().value()

    # --- model --> view
    def get_panel_view(self, model):
        return BudgetPanel(model, self.mainwindow)

    def refresh(self):
        self.startDateEdit.setText(self.model.start_date)
        self.repeatEverySpinBox.setValue(self.model.repeat_every)

    def refresh_repeat_every(self):
        self.repeatEveryDescLabel.setText(self.model.repeat_every_desc)

