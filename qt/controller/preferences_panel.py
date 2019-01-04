# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QDialog, QMessageBox, QVBoxLayout, QFormLayout, QLabel, QSpinBox, QCheckBox,
    QLineEdit, QDialogButtonBox
)

from core.trans import trget
from core.model.date import clean_format

from ..util import verticalSpacer, horizontalWrap

tr = trget('ui')

class PreferencesPanel(QDialog):
    def __init__(self, parent, app):
        # The flags we pass are that so we don't get the "What's this" button in the title bar
        QDialog.__init__(self, parent, Qt.WindowTitleHint | Qt.WindowSystemMenuHint)
        self.app = app
        self._setupUi()

        self.dateFormatEdit.editingFinished.connect(self.dateFormatEdited)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Preferences"))
        self.resize(332, 170)
        self.verticalLayout = QVBoxLayout(self)
        self.formLayout = QFormLayout()

        self.autoSaveIntervalSpinBox = QSpinBox(self)
        self.autoSaveIntervalSpinBox.setMaximumSize(QSize(70, 0xffffff))
        self.label_5 = QLabel(tr("step(s) (0 for none)"), self)
        self.formLayout.addRow(
            tr("Auto-save interval:"),
            horizontalWrap([self.autoSaveIntervalSpinBox, self.label_5])
        )

        self.dateFormatEdit = QLineEdit(self)
        self.dateFormatEdit.setMaximumSize(QSize(140, 0xffffff))
        self.formLayout.addRow(tr("Date format:"), self.dateFormatEdit)

        self.fontSizeSpinBox = QSpinBox()
        self.fontSizeSpinBox.setMinimum(5)
        self.fontSizeSpinBox.setMaximumSize(QSize(70, 0xffffff))
        self.formLayout.addRow(tr("Font size:"), self.fontSizeSpinBox)

        self.verticalLayout.addLayout(self.formLayout)

        self.scopeDialogCheckBox = QCheckBox(tr("Show scope dialog when modifying a scheduled transaction"), self)
        self.verticalLayout.addWidget(self.scopeDialogCheckBox)
        self.autoDecimalPlaceCheckBox = QCheckBox(tr("Automatically place decimals when typing"), self)
        self.verticalLayout.addWidget(self.autoDecimalPlaceCheckBox)
        self.dateEntryBox = QCheckBox(tr("Enter dates in day → month → year order"), self)
        self.verticalLayout.addWidget(self.dateEntryBox)
        self.verticalLayout.addItem(verticalSpacer())
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.verticalLayout.addWidget(self.buttonBox)

    def load(self):
        appm = self.app.model
        self.autoSaveIntervalSpinBox.setValue(appm.autosave_interval)
        self.dateFormatEdit.setText(self.app.prefs.dateFormat)
        self.fontSizeSpinBox.setValue(self.app.prefs.tableFontSize)
        self.scopeDialogCheckBox.setChecked(appm.show_schedule_scope_dialog)
        self.autoDecimalPlaceCheckBox.setChecked(appm.auto_decimal_place)
        self.dateEntryBox.setChecked(appm.day_first_date_entry)

    def save(self):
        restartRequired = False
        appm = self.app.model
        appm.autosave_interval = self.autoSaveIntervalSpinBox.value()
        if self.dateFormatEdit.text() != self.app.prefs.dateFormat:
            restartRequired = True
        self.app.prefs.dateFormat = self.dateFormatEdit.text()
        self.app.prefs.tableFontSize = self.fontSizeSpinBox.value()
        appm.show_schedule_scope_dialog = self.scopeDialogCheckBox.isChecked()
        appm.auto_decimal_place = self.autoDecimalPlaceCheckBox.isChecked()
        appm.day_first_date_entry = self.dateEntryBox.isChecked()
        if restartRequired:
            QMessageBox.information(self, "", tr("moneyGuru has to restart for these changes to take effect"))

    # --- Signals
    def dateFormatEdited(self):
        self.dateFormatEdit.setText(clean_format(self.dateFormatEdit.text()))


if __name__ == '__main__':
    import sys
    from PyQt5.QtWidgets import QApplication, QDialog
    app = QApplication([])
    dialog = QDialog(None)
    PreferencesPanel._setupUi(dialog)
    dialog.show()
    sys.exit(app.exec_())
