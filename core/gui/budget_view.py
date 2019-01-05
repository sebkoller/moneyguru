# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from core.trans import tr
from ..const import PaneType
from .base import BaseView
from .budget_table import BudgetTable
from .budget_panel import BudgetPanel

class BudgetView(BaseView):
    # --- model -> view calls:
    # get_panel_view(panel_model) -> view
    #

    VIEW_TYPE = PaneType.Budget
    PRINT_TITLE_FORMAT = tr('Budgets from {start_date} to {end_date}')

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.table = BudgetTable(self)
        self.restore_subviews_size()

    def _revalidate(self):
        self.table.refresh_and_show_selection()

    # --- Override
    def save_preferences(self):
        self.table.columns.save_columns()

    # --- Public
    def new_item(self):
        budget_panel = BudgetPanel(self.mainwindow)
        budget_panel.view = weakref.proxy(self.view.get_panel_view(budget_panel))
        budget_panel.new()
        return budget_panel

    def edit_item(self):
        budget_panel = BudgetPanel(self.mainwindow)
        budget_panel.view = weakref.proxy(self.view.get_panel_view(budget_panel))
        budget_panel.load()
        return budget_panel

    def delete_item(self):
        self.table.delete()

