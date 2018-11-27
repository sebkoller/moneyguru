# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QFormLayout, QLabel, QLineEdit, QComboBox, QSizePolicy,
    QPlainTextEdit, QDialogButtonBox, QTabWidget, QSpinBox, QAbstractItemView, QSpacerItem,
    QPushButton
)

from hscommon.trans import trget

from ..support.item_view import TableView
from ..support.date_edit import DateEdit
from ..support.completable_edit import PayeeEdit, DescriptionEdit
from .panel import Panel
from .selectable_list import ComboboxModel
from .split_table import SplitTable

tr = trget('ui')

class SchedulePanel(Panel):
    FIELDS = [
        ('startDateEdit', 'start_date'),
        ('repeatEverySpinBox', 'repeat_every'),
        ('stopDateEdit', 'stop_date'),
        ('descriptionEdit', 'description'),
        ('payeeEdit', 'payee'),
        ('checkNoEdit', 'checkno'),
        ('notesEdit', 'notes'),
    ]
    PERSISTENT_NAME = 'schedulePanel'

    def __init__(self, model, mainwindow):
        Panel.__init__(self, mainwindow)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.model = model
        self._setupUi()
        self.splitTable = SplitTable(model=self.model.split_table, view=self.splitTableView)
        self.repeatTypeComboBox = ComboboxModel(model=self.model.repeat_type_list, view=self.repeatTypeComboBoxView)

        self.addSplitButton.clicked.connect(self.splitTable.model.add)
        self.removeSplitButton.clicked.connect(self.splitTable.model.delete)
        self.buttonBox.accepted.connect(self.accept)
        self.buttonBox.rejected.connect(self.reject)

    def _setupUi(self):
        self.setWindowTitle(tr("Schedule Info"))
        self.resize(469, 416)
        self.setModal(True)
        self.verticalLayout_2 = QVBoxLayout(self)
        self.tabWidget = QTabWidget(self)
        self.tab = QWidget()
        self.formLayout = QFormLayout(self.tab)
        self.formLayout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.label_2 = QLabel(tr("Start Date:"))
        self.formLayout.setWidget(0, QFormLayout.LabelRole, self.label_2)
        self.startDateEdit = DateEdit(self.tab)
        self.startDateEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(0, QFormLayout.FieldRole, self.startDateEdit)
        self.label_7 = QLabel(tr("Repeat Type:"))
        self.formLayout.setWidget(1, QFormLayout.LabelRole, self.label_7)
        self.repeatTypeComboBoxView = QComboBox(self.tab)
        self.formLayout.setWidget(1, QFormLayout.FieldRole, self.repeatTypeComboBoxView)
        self.label_8 = QLabel(tr("Every:"))
        self.formLayout.setWidget(2, QFormLayout.LabelRole, self.label_8)
        self.horizontalLayout_2 = QHBoxLayout()
        self.repeatEverySpinBox = QSpinBox(self.tab)
        self.repeatEverySpinBox.setMinimum(1)
        self.horizontalLayout_2.addWidget(self.repeatEverySpinBox)
        self.repeatEveryDescLabel = QLabel(self.tab)
        self.horizontalLayout_2.addWidget(self.repeatEveryDescLabel)
        self.formLayout.setLayout(2, QFormLayout.FieldRole, self.horizontalLayout_2)
        self.label_9 = QLabel(tr("Stop Date:"))
        self.formLayout.setWidget(3, QFormLayout.LabelRole, self.label_9)
        self.stopDateEdit = DateEdit(self.tab, is_clearable=True)
        self.stopDateEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(3, QFormLayout.FieldRole, self.stopDateEdit)
        self.label_3 = QLabel(tr("Description:"))
        self.formLayout.setWidget(4, QFormLayout.LabelRole, self.label_3)
        self.descriptionEdit = DescriptionEdit(self.model.completable_edit, self.tab)
        self.formLayout.setWidget(4, QFormLayout.FieldRole, self.descriptionEdit)
        self.label_4 = QLabel(tr("Payee:"))
        self.formLayout.setWidget(5, QFormLayout.LabelRole, self.label_4)
        self.payeeEdit = PayeeEdit(self.model.completable_edit, self.tab)
        self.formLayout.setWidget(5, QFormLayout.FieldRole, self.payeeEdit)
        self.label_5 = QLabel(tr("Check #:"))
        self.formLayout.setWidget(6, QFormLayout.LabelRole, self.label_5)
        self.checkNoEdit = QLineEdit(self.tab)
        self.checkNoEdit.setMaximumSize(QSize(120, 16777215))
        self.formLayout.setWidget(6, QFormLayout.FieldRole, self.checkNoEdit)
        self.amountLabel = QLabel(tr("Transfers:"))
        self.formLayout.setWidget(7, QFormLayout.LabelRole, self.amountLabel)
        self.splitTableView = TableView(self.tab)
        self.splitTableView.setMinimumSize(QSize(355, 0))
        self.splitTableView.setAcceptDrops(True)
        self.splitTableView.setDragEnabled(True)
        self.splitTableView.setDragDropOverwriteMode(False)
        self.splitTableView.setDragDropMode(QAbstractItemView.InternalMove)
        self.splitTableView.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.splitTableView.horizontalHeader().setDefaultSectionSize(40)
        self.splitTableView.verticalHeader().setVisible(False)
        self.splitTableView.verticalHeader().setDefaultSectionSize(18)
        self.formLayout.setWidget(7, QFormLayout.FieldRole, self.splitTableView)
        self.widget = QWidget(self.tab)
        sizePolicy = QSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.widget.sizePolicy().hasHeightForWidth())
        self.widget.setSizePolicy(sizePolicy)
        self.horizontalLayout_6 = QHBoxLayout(self.widget)
        self.horizontalLayout_6.setContentsMargins(0, 0, 0, 0)
        spacerItem = QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.horizontalLayout_6.addItem(spacerItem)
        self.addSplitButton = QPushButton(self.widget)
        icon = QIcon()
        icon.addPixmap(QPixmap(':/plus_8'), QIcon.Normal, QIcon.Off)
        self.addSplitButton.setIcon(icon)
        self.horizontalLayout_6.addWidget(self.addSplitButton)
        self.removeSplitButton = QPushButton(self.widget)
        icon1 = QIcon()
        icon1.addPixmap(QPixmap(':/minus_8'), QIcon.Normal, QIcon.Off)
        self.removeSplitButton.setIcon(icon1)
        self.horizontalLayout_6.addWidget(self.removeSplitButton)
        self.formLayout.setWidget(8, QFormLayout.FieldRole, self.widget)
        self.tabWidget.addTab(self.tab, tr("Info"))
        self.tab_3 = QWidget()
        self.horizontalLayout_5 = QHBoxLayout(self.tab_3)
        self.notesEdit = QPlainTextEdit(self.tab_3)
        self.horizontalLayout_5.addWidget(self.notesEdit)
        self.tabWidget.addTab(self.tab_3, tr("Notes"))
        self.verticalLayout_2.addWidget(self.tabWidget)
        self.buttonBox = QDialogButtonBox(self)
        self.buttonBox.setOrientation(Qt.Horizontal)
        self.buttonBox.setStandardButtons(QDialogButtonBox.Cancel|QDialogButtonBox.Save)
        self.verticalLayout_2.addWidget(self.buttonBox)
        self.label_2.setBuddy(self.startDateEdit)
        self.label_7.setBuddy(self.repeatTypeComboBoxView)
        self.label_3.setBuddy(self.descriptionEdit)
        self.label_4.setBuddy(self.payeeEdit)
        self.label_5.setBuddy(self.checkNoEdit)

        self.tabWidget.setCurrentIndex(0)

    def _loadFields(self):
        Panel._loadFields(self)
        self.tabWidget.setCurrentIndex(0)

    # --- model --> view
    def refresh_for_multi_currency(self):
        pass

    def refresh_repeat_every(self):
        self.repeatEveryDescLabel.setText(self.model.repeat_every_desc)

