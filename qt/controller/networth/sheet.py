# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt

from ..column import Column
from ..account_sheet import AccountSheet

class NetWorthSheet(AccountSheet):
    COLUMNS = [
        Column('name', 133),
        Column('account_number', 80),
        Column('end', 100, alignment=Qt.AlignRight),
        Column('start', 100, alignment=Qt.AlignRight),
        Column('delta', 100, alignment=Qt.AlignRight),
        Column('delta_perc', 100),
    ]
    AMOUNT_ATTRS = {'end', 'start', 'delta', 'delta_perc'}
    BOLD_ATTRS = {'end'}

