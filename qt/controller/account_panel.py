# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtWidgets import (
    QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QSizePolicy, QPlainTextEdit,
    QCheckBox, QDialogButtonBox
)

from core.trans import trget

from .panel import Panel
from .selectable_list import ComboboxModel

tr = trget('ui')

class AccountPanel(Panel):
    FIELDS = [
        ('nameEdit', 'name'),
        ('accountNumberEdit', 'account_number'),
        ('inactiveBox', 'inactive'),
        ('notesEdit', 'notes'),
    ]
    PERSISTENT_NAME = 'accountPanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._setupUi()
        self.model = model
        self.typeComboBox = ComboboxModel(model=self.model.type_list, view=self.typeComboBoxView)
        self.currencyComboBox = ComboboxModel(model=self.model.currency_list, view=self.currencyComboBoxView)

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Account Info"))
        self.resize(274, 121)
        self.setModal(True)
        self.verticalLayout = QVBoxLayout(self)
        self.formLayout = QFormLayout()
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.label = QLabel(tr("Name"))
        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label)
        self.nameEdit = QLineEdit()
        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.nameEdit)
        self.label_2 = QLabel(tr("Type"))
        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_2)
        self.typeComboBoxView = QComboBox()
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.typeComboBoxView)
        self.label_3 = QLabel(tr("Currency"))
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_3)
        self.currencyComboBoxView = QComboBox()
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.currencyComboBoxView.sizePolicy().hasHeightForWidth())
        self.currencyComboBoxView.setSizePolicy(sizePolicy)
        self.currencyComboBoxView.setEditable(True)
        self.currencyComboBoxView.setInsertPolicy(QComboBox.NoInsert)
        self.formLayout.setWidget(2, QFormLayout.FieldRole, self.currencyComboBoxView)
        self.accountNumberLabel = QLabel(tr("Account #"))
        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.accountNumberLabel)
        self.accountNumberEdit = QLineEdit()
        self.accountNumberEdit.setMaximumSize(QSize(80, 16777215))
        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.accountNumberEdit)
        self.inactiveBox = QCheckBox()
        self.formLayout.addRow(tr("Inactive:"), self.inactiveBox)
        self.notesEdit = QPlainTextEdit()
        self.formLayout.addRow(tr("Notes:"), self.notesEdit)
        self.verticalLayout.addLayout(self.formLayout)
        self.buttonBox = QDialogButtonBox()
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Save)
        self.verticalLayout.addWidget(self.buttonBox)
        self.label.setBuddy(self.nameEdit)
        self.label_2.setBuddy(self.typeComboBoxView)
        self.label_3.setBuddy(self.currencyComboBoxView)

    def _loadFields(self):
        Panel._loadFields(self)
        self.currencyComboBoxView.setEnabled(self.model.can_change_currency)

