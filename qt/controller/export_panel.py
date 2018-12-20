# Created By: Virgil Dupras
# Created On: 2010-10-25
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout, QLabel, QButtonGroup, QRadioButton, QTableView, QAbstractItemView,
    QDialogButtonBox, QApplication, QDialog, QFileDialog, QCheckBox
)

from core.trans import trget
from core.gui.export_panel import ExportFormat

from .panel import Panel
from .export_account_table import ExportAccountTable

tr = trget('ui')

class ExportType:
    All = 0
    Selected = 1

class ExportPanel(Panel):
    FIELDS = []
    PERSISTENT_NAME = 'exportPanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.mainwindow = mainwindow
        self._setupUi()
        self.model = model
        self.accountTable = ExportAccountTable(model=self.model.account_table, view=self.tableView)

        self.exportTypeButtons.buttonClicked[int].connect(self.exportTypeSelected)
        self.exportFormatButtons.buttonClicked[int].connect(self.exportFormatSelected)
        self.buttonBox.rejected.connect(self.reject)
        self.exportButton.clicked.connect(self.exportButtonClicked)

    def _setupUi(self):
        self.setWindowTitle(tr("Export Options"))
        self.mainLayout = QVBoxLayout(self)

        self.label1 = QLabel(tr("Which accounts do you want to export?"), self)
        self.mainLayout.addWidget(self.label1)
        self.exportTypeButtons = QButtonGroup(self)
        self.exportAllButton = QRadioButton(tr("All"), self)
        self.mainLayout.addWidget(self.exportAllButton)
        self.exportTypeButtons.addButton(self.exportAllButton, ExportType.All)
        self.exportAllButton.setChecked(True)
        self.exportSelectedButton = QRadioButton(tr("Selected"), self)
        self.mainLayout.addWidget(self.exportSelectedButton)
        self.exportTypeButtons.addButton(self.exportSelectedButton, ExportType.Selected)

        self.tableView = QTableView(self)
        self.tableView.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tableView.verticalHeader().setVisible(False)
        self.tableView.verticalHeader().setDefaultSectionSize(18)
        self.mainLayout.addWidget(self.tableView)

        self.label2 = QLabel(tr("Export format:"), self)
        self.mainLayout.addWidget(self.label2)
        self.exportFormatButtons = QButtonGroup(self)
        self.exportAsQIFButton = QRadioButton("QIF", self)
        self.mainLayout.addWidget(self.exportAsQIFButton)
        self.exportFormatButtons.addButton(self.exportAsQIFButton, ExportFormat.QIF)
        self.exportAsQIFButton.setChecked(True)
        self.exportAsCSVButton = QRadioButton("CSV", self)
        self.mainLayout.addWidget(self.exportAsCSVButton)
        self.exportFormatButtons.addButton(self.exportAsCSVButton, ExportFormat.CSV)

        self.label3 = QLabel(tr("Export scope:"))
        self.mainLayout.addWidget(self.label3)
        self.dateRangeOnlyCheckbox = QCheckBox(tr("Current date range only"))
        self.mainLayout.addWidget(self.dateRangeOnlyCheckbox)

        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel)
        self.exportButton = self.buttonBox.addButton(tr("Export"), QDialogButtonBox.ActionRole)
        self.mainLayout.addWidget(self.buttonBox)

    # --- Overrides
    def _loadFields(self):
        self.exportAllButton.setChecked(self.model.export_all)
        self.exportAsQIFButton.setChecked(self.model.export_format == ExportFormat.QIF)
        self.dateRangeOnlyCheckbox.setChecked(self.model.current_daterange_only)

    def _saveFields(self):
        self.model.current_daterange_only = self.dateRangeOnlyCheckbox.isChecked()

    # --- Event Handlers
    def exportButtonClicked(self):
        title = tr("Export")
        fileext = 'qif' if self.model.export_format == ExportFormat.QIF else 'csv'
        filters = tr("{0} Files (*.{1})").format(fileext.upper(), fileext)
        filename = 'export.{0}'.format(fileext)
        docpath = QFileDialog.getSaveFileName(self.mainwindow, title, filename, filters)[0]
        if docpath:
            self.model.export_path = docpath
            self.accept()

    def exportTypeSelected(self, typeId):
        self.model.export_all = typeId == ExportType.All

    def exportFormatSelected(self, typeId):
        self.model.export_format = typeId

    # --- model --> view
    def set_table_enabled(self, enabled):
        self.tableView.setEnabled(enabled)

    def set_export_button_enabled(self, enabled):
        self.exportButton.setEnabled(enabled)


if __name__ == '__main__':
    import sys
    app = QApplication([])
    dialog = QDialog(None)
    ExportPanel._setupUi(dialog)
    dialog.show()
    sys.exit(app.exec_())
