# Created By: Virgil Dupras
# Created On: 2009-12-10
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton, QSpacerItem, QSizePolicy
)

from core.trans import trget

from core.document import ScheduleScope

tr = trget('ui')

class ScheduleScopeDialog(QDialog):
    def __init__(self, parent=None):
        # The flags we pass are that so we don't get the "What's this" button in the title bar
        QDialog.__init__(self, None, Qt.WindowTitleHint | Qt.WindowSystemMenuHint)
        self._setupUi()
        self._result = ScheduleScope.Local

        self.cancelButton.clicked.connect(self.cancelClicked)
        self.globalScopeButton.clicked.connect(self.globalScopeClicked)
        self.localScopeButton.clicked.connect(self.localScopeClicked)

    def _setupUi(self):
        self.setWindowTitle(tr("Schedule Modification Scope"))
        self.resize(333, 133)
        self.verticalLayout = QVBoxLayout(self)
        self.label = QLabel(tr("Do you want this change to affect all future occurrences of this schedule?"))
        font = QFont()
        font.setWeight(75)
        font.setBold(True)
        self.label.setFont(font)
        self.label.setWordWrap(True)
        self.verticalLayout.addWidget(self.label)
        self.label_2 = QLabel(tr(
            "You can force global scope (in other words, changing all future occurrences) by "
            "holding Shift when you perform the change."
        ))
        self.label_2.setWordWrap(True)
        self.verticalLayout.addWidget(self.label_2)
        self.horizontalLayout = QHBoxLayout()
        self.cancelButton = QPushButton(tr("Cancel"))
        self.cancelButton.setShortcut("Esc")
        self.horizontalLayout.addWidget(self.cancelButton)
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout.addItem(spacerItem)
        self.globalScopeButton = QPushButton(tr("All future occurrences"))
        self.globalScopeButton.setAutoDefault(False)
        self.horizontalLayout.addWidget(self.globalScopeButton)
        self.localScopeButton = QPushButton(tr("Just this one"))
        self.localScopeButton.setAutoDefault(False)
        self.localScopeButton.setDefault(True)
        self.horizontalLayout.addWidget(self.localScopeButton)
        self.verticalLayout.addLayout(self.horizontalLayout)

    def cancelClicked(self):
        self._result = ScheduleScope.Cancel
        self.accept()

    def globalScopeClicked(self):
        self._result = ScheduleScope.Global
        self.accept()

    def localScopeClicked(self):
        self._result = ScheduleScope.Local
        self.accept()

    def queryForScope(self):
        self.exec_()
        return self._result

