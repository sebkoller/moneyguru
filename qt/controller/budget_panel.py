# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QPlainTextEdit,
    QDialogButtonBox, QSpinBox
)

from core.trans import trget

from ..support.date_edit import DateEdit
from .panel import Panel
from .selectable_list import ComboboxModel

tr = trget('ui')

class BudgetPanel(Panel):
    FIELDS = [
        ('startDateEdit', 'start_date'),
        ('repeatEverySpinBox', 'repeat_every'),
        ('stopDateEdit', 'stop_date'),
        ('amountEdit', 'amount'),
        ('notesEdit', 'notes'),
    ]
    PERSISTENT_NAME = 'budgetPanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._setupUi()
        self.model = model
        self.repeatTypeComboBox = ComboboxModel(model=self.model.repeat_type_list, view=self.repeatTypeComboBoxView)
        self.accountComboBox = ComboboxModel(model=self.model.account_list, view=self.accountComboBoxView)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Budget Info"))
        self.resize(230, 369)
        self.setModal(True)
        self.verticalLayout = QVBoxLayout(self)
        self.formLayout = QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.label_2 = QLabel(tr("Start Date:"))
        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_2)
        self.startDateEdit = DateEdit(self)
        self.startDateEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.startDateEdit)
        self.label_7 = QLabel(tr("Repeat Type:"))
        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_7)
        self.repeatTypeComboBoxView = QComboBox(self)
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.repeatTypeComboBoxView)
        self.label_8 = QLabel(tr("Every:"))
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_8)
        self.horizontalLayout_2 = QHBoxLayout()
        self.repeatEverySpinBox = QSpinBox(self)
        self.repeatEverySpinBox.setMinimum(1)
        self.horizontalLayout_2.addWidget(self.repeatEverySpinBox)
        self.repeatEveryDescLabel = QLabel(self)
        self.horizontalLayout_2.addWidget(self.repeatEveryDescLabel)
        self.formLayout.setLayout(2, QFormLayout.FieldRole, self.horizontalLayout_2)
        self.label_9 = QLabel(tr("Stop Date:"))
        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_9)
        self.stopDateEdit = DateEdit(self)
        self.stopDateEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.stopDateEdit)
        self.accountComboBoxView = QComboBox(self)
        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.accountComboBoxView)
        self.label_3 = QLabel(tr("Account:"))
        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_3)
        self.amountEdit = QLineEdit(self)
        self.amountEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.amountEdit)
        self.label_5 = QLabel(tr("Amount:"))
        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_5)
        self.notesEdit = QPlainTextEdit(tr("Notes:"))
        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.notesEdit)
        self.label = QLabel(self)
        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.label)
        self.verticalLayout.addLayout(self.formLayout)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Save)
        self.verticalLayout.addWidget(self.buttonBox)
        self.label_2.setBuddy(self.startDateEdit)
        self.label_7.setBuddy(self.repeatTypeComboBoxView)
        self.label_8.setBuddy(self.repeatEverySpinBox)
        self.label_9.setBuddy(self.stopDateEdit)
        self.label_3.setBuddy(self.accountComboBoxView)
        self.label_5.setBuddy(self.amountEdit)

    # --- model --> view
    def refresh_repeat_every(self):
        self.repeatEveryDescLabel.setText(self.model.repeat_every_desc)

