# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt

from ..column import Column
from ..table import Table, AMOUNT_PAINTER

class BudgetTable(Table):
    COLUMNS = [
        Column('account', 144),
        Column('amount', 100, alignment=Qt.AlignRight, painter=AMOUNT_PAINTER, resizeToFit=True),
    ]

    def __init__(self, model, view):
        Table.__init__(self, model, view)
        self.view.deletePressed.connect(self.model.delete)
        self.view.doubleClicked.connect(self.model.edit)
        # we have to prevent Return from initiating editing.
        self.view.editSelected = lambda: None

