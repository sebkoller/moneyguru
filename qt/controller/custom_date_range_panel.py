# Created By: Virgil Dupras
# Created On: 2009-11-11
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSizePolicy, QSpacerItem, QLineEdit,
    QDialogButtonBox
)

from core.trans import trget

from ..support.date_edit import DateEdit
from .panel import Panel

tr = trget('ui')

class CustomDateRangePanel(Panel):
    FIELDS = [
        ('startDateEdit', 'start_date'),
        ('endDateEdit', 'end_date'),
        ('slotIndexComboBox', 'slot_index'),
        ('slotNameEdit', 'slot_name'),
    ]
    PERSISTENT_NAME = 'customDateRangePanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self._setupUi()
        self.model = model

        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Custom Date Range"))
        self.resize(292, 86)
        self.setModal(True)
        self.verticalLayout = QVBoxLayout(self)
        self.label = QLabel(tr("Select start and end dates from your custom range:"))
        self.verticalLayout.addWidget(self.label)
        self.horizontalLayout = QHBoxLayout()
        self.label_2 = QLabel(tr("Start:"))
        self.horizontalLayout.addWidget(self.label_2)
        self.startDateEdit = DateEdit(self)
        self.horizontalLayout.addWidget(self.startDateEdit)
        self.label_3 = QLabel(tr("End:"))
        self.horizontalLayout.addWidget(self.label_3)
        self.endDateEdit = DateEdit(self)
        self.horizontalLayout.addWidget(self.endDateEdit)
        self.verticalLayout.addLayout(self.horizontalLayout)
        self.horizontalLayout_2 = QHBoxLayout()
        self.label_4 = QLabel(tr("Save this range under slot:"))
        self.horizontalLayout_2.addWidget(self.label_4)
        self.slotIndexComboBox = QComboBox(self)
        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.slotIndexComboBox.sizePolicy().hasHeightForWidth())
        self.slotIndexComboBox.setSizePolicy(sizePolicy)
        for s in [tr("None"), tr("#1"), tr("#2"), tr("#3")]:
            self.slotIndexComboBox.addItem(s)
        self.horizontalLayout_2.addWidget(self.slotIndexComboBox)
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_2.addItem(spacerItem)
        self.verticalLayout.addLayout(self.horizontalLayout_2)
        self.horizontalLayout_3 = QHBoxLayout()
        self.label_5 = QLabel(tr("Under the name:"))
        self.horizontalLayout_3.addWidget(self.label_5)
        self.slotNameEdit = QLineEdit(self)
        sizePolicy = QSizePolicy(QSizePolicy.MinimumExpanding, QSizePolicy.Fixed)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.slotNameEdit.sizePolicy().hasHeightForWidth())
        self.slotNameEdit.setSizePolicy(sizePolicy)
        self.horizontalLayout_3.addWidget(self.slotNameEdit)
        self.verticalLayout.addLayout(self.horizontalLayout_3)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Ok)
        self.verticalLayout.addWidget(self.buttonBox)

