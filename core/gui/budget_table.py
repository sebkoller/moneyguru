# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime

from core.trans import trget
from .column import Column

from .table import GUITable, Row, rowattr, TableWithAmountMixin

trcol = trget('columns')

class BudgetTable(GUITable, TableWithAmountMixin):
    SAVENAME = 'BudgetTable'
    COLUMNS = [
        Column('start_date', display=trcol("Start Date")),
        Column('stop_date', display=trcol("Stop Date")),
        Column('repeat_type', display=trcol("Repeat Type")),
        Column('interval', display=trcol("Interval")),
        Column('account', display=trcol("Account")),
        Column('amount', display=trcol("Amount")),
    ]

    def __init__(self, budget_view):
        GUITable.__init__(self, document=budget_view.document)
        self.mainwindow = budget_view.mainwindow

    # --- Override
    def _update_selection(self):
        self.mainwindow.selected_budgets = self.selected_budgets

    def _fill(self):
        self._all_amounts_are_native = True
        for budget in self.document.budgets:
            if not self.mainwindow.document.is_amount_native(budget.amount):
                self._all_amounts_are_native = False
            self.append(BudgetTableRow(self, budget))

    # --- Public
    def delete(self):
        self.document.delete_budgets(self.selected_budgets)
        self.mainwindow.revalidate()

    def edit(self):
        self.mainwindow.edit_item()

    # --- Properties
    @property
    def selected_budgets(self):
        return [row.budget for row in self.selected_rows]


class BudgetTableRow(Row):
    def __init__(self, table, budget):
        Row.__init__(self, table)
        self.document = table.document
        self.budget = budget
        self.load()

    # --- Public
    def load(self):
        budget = self.budget
        self._start_date = budget.start_date
        self._start_date_fmt = self.document.app.format_date(self._start_date)
        self._stop_date = budget.stop_date
        self._stop_date_fmt = self.document.app.format_date(self._stop_date) if self._stop_date is not None else ''
        self._repeat_type = budget.repeat_type_desc
        self._interval = str(budget.repeat_every)
        self._account = budget.account.name
        self._amount = budget.amount
        self._amount_fmt = self.document.format_amount(self._amount)

    def save(self):
        pass # read-only

    def sort_key_for_column(self, column_name):
        if column_name == 'stop_date' and self._stop_date is None:
            return datetime.date.min
        else:
            return Row.sort_key_for_column(self, column_name)

    # --- Properties
    start_date = rowattr('_start_date_fmt')
    stop_date = rowattr('_stop_date_fmt')
    repeat_type = rowattr('_repeat_type')
    interval = rowattr('_interval')
    account = rowattr('_account')
    amount = rowattr('_amount_fmt')

