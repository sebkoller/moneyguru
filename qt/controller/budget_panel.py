# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPlainTextEdit,
    QDialogButtonBox
)

from core.trans import trget

from .panel import Panel
from .selectable_list import ComboboxModel

tr = trget('ui')

class BudgetPanel(Panel):
    FIELDS = [
        ('amountEdit', 'amount'),
        ('notesEdit', 'notes'),
    ]
    PERSISTENT_NAME = 'budgetPanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._setupUi()
        self.model = model
        self.accountComboBox = ComboboxModel(model=self.model.account_list, view=self.accountComboBoxView)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Budget Info"))
        self.resize(230, 230)
        self.setModal(True)
        self.verticalLayout = QVBoxLayout(self)
        self.formLayout = QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.accountComboBoxView = QComboBox(self)
        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.accountComboBoxView)
        self.label_3 = QLabel(tr("Account:"))
        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_3)
        self.amountEdit = QLineEdit(self)
        self.amountEdit.setMaximumWidth(120)
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.amountEdit)
        self.label_5 = QLabel(tr("Amount:"))
        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_5)
        self.notesEdit = QPlainTextEdit(tr("Notes:"))
        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.notesEdit)
        self.label = QLabel(self)
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label)
        self.verticalLayout.addLayout(self.formLayout)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Save)
        self.verticalLayout.addWidget(self.buttonBox)
        self.label_3.setBuddy(self.accountComboBoxView)
        self.label_5.setBuddy(self.amountEdit)
