# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog, QTabBar, QComboBox, QGroupBox, QPushButton, QVBoxLayout, QSpinBox,
    QHBoxLayout, QSpacerItem, QLabel, QSizePolicy, QCheckBox, QAbstractItemView
)

from core.trans import trget

from ...support.item_view import TableView
from ...util import horizontalWrap, horizontalSpacer
from ..selectable_list import ComboboxModel
from .table import ImportTable

tr = trget('ui')

class ImportWindow(QDialog):
    def __init__(self, model, mainwindow, prefs):
        QDialog.__init__(self, mainwindow, Qt.Window)
        self.prefs = prefs
        self._setupUi()
        self.prefs.restoreGeometry('importWindowGeometry', self)
        self.doc = mainwindow.doc
        self.model = model
        self.swapOptionsComboBox = ComboboxModel(model=self.model.swap_type_list, view=self.swapOptionsComboBoxView)
        self.table = ImportTable(model=self.model.import_table, view=self.tableView)
        self._setupColumns() # Can only be done after the model has been connected

        self.targetAccountComboBox.addItems(self.model.target_account_names)
        for pane in self.model.panes:
            self.tabView.addTab(pane.name)

        self.tabView.tabCloseRequested.connect(self.tabCloseRequested)
        self.tabView.currentChanged.connect(self.currentTabChanged)
        self.targetAccountComboBox.currentIndexChanged.connect(self.targetAccountChanged)
        self.closeButton.clicked.connect(self.close)
        self.importButton.clicked.connect(self.importClicked)
        self.matchButton.clicked.connect(self.matchClicked)
        self.swapButton.clicked.connect(self.swapClicked)

    def _setupUi(self):
        self.setWindowTitle(tr("Import"))
        self.resize(557, 407)
        self.setModal(True)
        self.verticalLayout = QVBoxLayout(self)
        self.tabView = QTabBar(self)
        self.tabView.setMinimumHeight(20)
        self.verticalLayout.addWidget(self.tabView)
        self.targetAccountLayout = QHBoxLayout()
        self.targetAccountLabel = QLabel(tr("Target Account:"))
        self.targetAccountLayout.addWidget(self.targetAccountLabel)
        self.targetAccountComboBox = QComboBox(self)
        self.targetAccountComboBox.setMinimumWidth(150)
        self.targetAccountLayout.addWidget(self.targetAccountComboBox)
        self.targetAccountLayout.addItem(horizontalSpacer())

        self.matchBox = QGroupBox(tr("Match entries by date/amount"))
        self.matchBox.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        matchLayout = QVBoxLayout(self.matchBox)
        self.matchThreshold = QSpinBox()
        label = QLabel(tr("maximum day(s)"))
        matchLayout.addLayout(horizontalWrap([self.matchThreshold, label]))
        self.matchButton = QPushButton(tr("Match"))
        self.matchButton.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Preferred)
        matchLayout.addLayout(horizontalWrap([None, self.matchButton]))

        self.targetAccountLayout.addWidget(self.matchBox)
        self.swapBox = QGroupBox(tr("Are some fields wrong? Fix them!"))
        swapLayout = QVBoxLayout(self.swapBox)
        self.swapOptionsComboBoxView = QComboBox(self.swapBox)
        swapLayout.addWidget(self.swapOptionsComboBoxView)
        self.applyToAllCheckBox = QCheckBox(tr("Apply to all accounts"))
        self.swapButton = QPushButton(tr("Fix"))
        swapLayout.addLayout(horizontalWrap([self.applyToAllCheckBox, self.swapButton]))
        self.targetAccountLayout.addWidget(self.swapBox)

        self.verticalLayout.addLayout(self.targetAccountLayout)
        self.tableView = TableView(self)
        self.tableView.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tableView.setDragEnabled(True)
        self.tableView.setDragDropMode(QAbstractItemView.InternalMove)
        self.tableView.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.horizontalHeader().setHighlightSections(False)
        self.tableView.horizontalHeader().setMinimumSectionSize(18)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.verticalHeader().setDefaultSectionSize(18)
        self.verticalLayout.addWidget(self.tableView)
        self.horizontalLayout = QHBoxLayout()
        spacerItem1 = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem1)
        self.closeButton = QPushButton(tr("Close"))
        self.horizontalLayout.addWidget(self.closeButton)
        self.importButton = QPushButton(tr("Import"))
        self.horizontalLayout.addWidget(self.importButton)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.tabView.setTabsClosable(True)
        self.tabView.setDrawBase(False)
        self.tabView.setDocumentMode(True)
        self.tabView.setUsesScrollButtons(True)

    def _setupColumns(self):
        # Can't set widget alignment in a layout in the Designer
        l = self.targetAccountLayout
        l.setAlignment(self.targetAccountLabel, Qt.AlignTop)
        l.setAlignment(self.targetAccountComboBox, Qt.AlignTop)

    # --- Event Handlers
    def close(self):
        self.prefs.saveGeometry('importWindowGeometry', self)
        super().close()

    def currentTabChanged(self, index):
        self.model.selected_pane_index = index

    def importClicked(self):
        self.model.import_selected_pane()

    def matchClicked(self):
        threshold = self.matchThreshold.value()
        self.model.match_entries_by_date_and_amount(threshold)

    def swapClicked(self):
        applyToAll = self.applyToAllCheckBox.isChecked()
        self.model.perform_swap(apply_to_all=applyToAll)

    def tabCloseRequested(self, index):
        self.model.close_pane(index)
        self.tabView.removeTab(index)

    def targetAccountChanged(self, index):
        self.model.selected_target_account_index = index
        self.table.updateColumnsVisibility()

    # --- model --> view
    def close_selected_tab(self):
        self.tabView.removeTab(self.tabView.currentIndex())

    def set_swap_button_enabled(self, enabled):
        self.swapButton.setEnabled(enabled)

    def update_selected_pane(self):
        index = self.model.selected_pane_index
        if index != self.tabView.currentIndex(): # this prevents infinite loops
            self.tabView.setCurrentIndex(index)
        self.targetAccountComboBox.setCurrentIndex(self.model.selected_target_account_index)
        self.table.updateColumnsVisibility()

