# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from core.trans import tr
from ..const import PaneType
from .base import BaseView
from .schedule_table import ScheduleTable
from .schedule_panel import SchedulePanel

class ScheduleView(BaseView):
    VIEW_TYPE = PaneType.Schedule
    PRINT_TITLE_FORMAT = tr('Schedules from {start_date} to {end_date}')

    def __init__(self, mainwindow):
        super().__init__(mainwindow)
        self.table = ScheduleTable(self)
        self.columns = self.table.columns
        self.restore_subviews_size()

    def _revalidate(self):
        self.table.refresh_and_show_selection()

    # --- Override
    def save_preferences(self):
        self.table.columns.save_columns()

    # --- Public
    def new_item(self):
        schedule_panel = SchedulePanel(self.mainwindow)
        schedule_panel.view = weakref.proxy(self.view.get_panel_view(schedule_panel))
        schedule_panel.new()
        return schedule_panel

    def edit_item(self):
        schedule_panel = SchedulePanel(self.mainwindow)
        schedule_panel.view = weakref.proxy(self.view.get_panel_view(schedule_panel))
        schedule_panel.load()
        return schedule_panel

    def delete_item(self):
        self.table.delete()

