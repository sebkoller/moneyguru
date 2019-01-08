# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QKeySequence, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QShortcut, QGridLayout, QPushButton, QLabel, QVBoxLayout
)

from core.trans import trget
from core.const import PaneType

from ..util import horizontalSpacer, verticalSpacer
from .base_view import BaseView

tr = trget('ui')

class NewView(BaseView):
    def _setup(self):
        self._setupUi()

        self.networthButton.clicked.connect(self.networthButtonClicked)
        self.profitButton.clicked.connect(self.profitButtonClicked)
        self.transactionButton.clicked.connect(self.transactionButtonClicked)
        self.gledgerButton.clicked.connect(self.gledgerButtonClicked)
        self.scheduleButton.clicked.connect(self.scheduleButtonClicked)
        self.budgetButton.clicked.connect(self.budgetButtonClicked)
        self.docpropsButton.clicked.connect(self.docpropsButtonClicked)
        self.shortcut1.activated.connect(self.networthButtonClicked)
        self.shortcut2.activated.connect(self.profitButtonClicked)
        self.shortcut3.activated.connect(self.transactionButtonClicked)
        self.shortcut4.activated.connect(self.gledgerButtonClicked)
        self.shortcut5.activated.connect(self.scheduleButtonClicked)
        self.shortcut6.activated.connect(self.budgetButtonClicked)
        self.shortcut7.activated.connect(self.docpropsButtonClicked)

    def _setupUi(self):
        self.resize(400, 300)
        self.gridLayout = QGridLayout(self)
        self.label = QLabel(tr("Choose a type for this tab:"))
        self.label.setAlignment(Qt.AlignCenter)
        self.gridLayout.addWidget(self.label, 0, 0, 1, 3)
        self.gridLayout.addItem(horizontalSpacer(), 1, 0, 1, 1)
        self.verticalLayout = QVBoxLayout()
        BUTTONS = [
            ('networthButton', tr("1. Net Worth"), 'balance_sheet_16'),
            ('profitButton', tr("2. Profit && Loss"), 'income_statement_16'),
            ('transactionButton', tr("3. Transactions"), 'transaction_table_16'),
            ('gledgerButton', tr("4. General Ledger"), 'gledger_16'),
            ('scheduleButton', tr("5. Schedules"), 'schedules_16'),
            ('budgetButton', tr("6. Budgets"), 'budget_16'),
            ('docpropsButton', tr("7. Document Properties"), 'gledger_16'),
        ]
        for i, (name, label, icon) in enumerate(BUTTONS, start=1):
            button = QPushButton(label)
            if icon:
                button.setIcon(QIcon(QPixmap(':/{}'.format(icon))))
            self.verticalLayout.addWidget(button)
            setattr(self, name, button)
            shortcut = QShortcut(self)
            shortcut.setKey(QKeySequence(str(i)))
            shortcut.setContext(Qt.WidgetShortcut)
            setattr(self, 'shortcut{}'.format(i), shortcut)
        self.gridLayout.addLayout(self.verticalLayout, 1, 1, 1, 1)
        self.gridLayout.addItem(horizontalSpacer(), 1, 2, 1, 1)
        self.gridLayout.addItem(verticalSpacer(), 2, 1, 1, 1)

    # --- Event Handlers
    def networthButtonClicked(self):
        self.model.select_pane_type(PaneType.NetWorth)

    def profitButtonClicked(self):
        self.model.select_pane_type(PaneType.Profit)

    def transactionButtonClicked(self):
        self.model.select_pane_type(PaneType.Transaction)

    def gledgerButtonClicked(self):
        self.model.select_pane_type(PaneType.GeneralLedger)

    def scheduleButtonClicked(self):
        self.model.select_pane_type(PaneType.Schedule)

    def budgetButtonClicked(self):
        self.model.select_pane_type(PaneType.Budget)

    def docpropsButtonClicked(self):
        self.model.select_pane_type(PaneType.DocProps)
