# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence
from PyQt5.QtWidgets import QWidget, QShortcut, QVBoxLayout, QListWidget, QAbstractItemView

from core.trans import trget

from ..support.search_edit import SearchEdit

tr = trget('ui')

class Lookup(QWidget):
    MODEL_CLASS = None

    def __init__(self, parent, model):
        QWidget.__init__(self, parent, Qt.Window)
        self.model = model
        self.model.view = self
        self._setupUi()

        self.searchEdit.searchChanged.connect(self.searchChanged)
        self.searchEdit.returnPressed.connect(self.returnPressed)
        self.namesList.currentRowChanged.connect(self.currentRowChanged)
        self.namesList.itemDoubleClicked.connect(self.itemDoubleClicked)
        self._shortcutUp.activated.connect(self.upPressed)
        self._shortcutDown.activated.connect(self.downPressed)

    def _setupUi(self):
        self.setWindowTitle(tr("Lookup"))
        self.resize(314, 331)
        self.verticalLayout = QVBoxLayout(self)
        self.searchEdit = SearchEdit(self)
        self.verticalLayout.addWidget(self.searchEdit)
        self.namesList = QListWidget(self)
        self.namesList.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.namesList.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.namesList.setUniformItemSizes(True)
        self.namesList.setSelectionRectVisible(True)
        self.verticalLayout.addWidget(self.namesList)

        self.searchEdit.immediate = True
        self._shortcutUp = QShortcut(self.searchEdit)
        self._shortcutUp.setKey(QKeySequence(Qt.Key_Up))
        self._shortcutUp.setContext(Qt.WidgetShortcut)
        self._shortcutDown = QShortcut(self.searchEdit)
        self._shortcutDown.setKey(QKeySequence(Qt.Key_Down))
        self._shortcutDown.setContext(Qt.WidgetShortcut)

    def _restoreSelection(self):
        self.namesList.setCurrentRow(self.model.selected_index)

    # --- Event Handlers
    def returnPressed(self):
        self.model.go()

    def searchChanged(self):
        self.model.search_query = str(self.searchEdit.text())

    def currentRowChanged(self, row):
        if row >= 0:
            self.model.selected_index = row

    def itemDoubleClicked(self, item):
        self.model.go()

    def upPressed(self):
        if self.namesList.currentRow() > 0:
            self.namesList.setCurrentRow(self.namesList.currentRow()-1)

    def downPressed(self):
        if self.namesList.currentRow() < self.namesList.count()-1:
            self.namesList.setCurrentRow(self.namesList.currentRow()+1)

    # --- model --> view
    def refresh(self):
        self.namesList.clear()
        self.namesList.addItems(self.model.names)
        self._restoreSelection()
        self.searchEdit.setText(self.model.search_query)

    def show(self):
        QWidget.show(self)
        self.searchEdit.setFocus()
        # see csv_options
        self.raise_()

    def hide(self):
        QWidget.hide(self)

