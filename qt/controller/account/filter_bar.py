# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.const import FilterType
from core.trans import trget

from ..filter_bar import FilterBar

tr = trget('ui')

class EntryFilterBar(FilterBar):
    BUTTONS = [
        (tr("All"), None),
        (tr("Increase"), FilterType.Income),
        (tr("Decrease"), FilterType.Expense),
        (tr("Transfers"), FilterType.Transfer),
        (tr("Unassigned"), FilterType.Unassigned),
        (tr("Reconciled"), FilterType.Reconciled),
        (tr("Not Reconciled"), FilterType.NotReconciled),
    ]

    # --- model --> view
    def disable_transfers(self):
        self.view.buttons[3].setEnabled(False)

    def enable_transfers(self):
        self.view.buttons[3].setEnabled(True)

