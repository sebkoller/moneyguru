# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt

from ..column import Column
from ..account_sheet import AccountSheet

class ProfitSheet(AccountSheet):
    COLUMNS = [
        Column('name', 133),
        Column('account_number', 80),
        Column('cash_flow', 100, alignment=Qt.AlignRight),
        Column('last_cash_flow', 100, alignment=Qt.AlignRight),
        Column('delta', 100, alignment=Qt.AlignRight),
        Column('delta_perc', 100),
        Column('budgeted', 100, alignment=Qt.AlignRight),
    ]
    AMOUNT_ATTRS = {'cash_flow', 'last_cash_flow', 'delta', 'delta_perc', 'budgeted'}
    BOLD_ATTRS = {'cash_flow', }

