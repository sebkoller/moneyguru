# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from .base import GUIPanel

class CustomDateRangePanel(GUIPanel):
    def __init__(self, drsel):
        GUIPanel.__init__(self, drsel.mainwindow)
        self.drsel = drsel
        self._start_date = date.today()
        self._end_date = date.today()

    # --- Override
    def _load(self):
        self._start_date = self.document.date_range.start
        self._end_date = self.document.date_range.end
        self.slot_index = 0 # 0 = None, 1 = Slot 1...
        self.slot_name = ''

    def _save(self):
        start = self._start_date
        end = self._end_date
        if self.slot_index > 0:
            self.drsel.save_custom_range(
                self.slot_index-1, self.slot_name, start, end)
        self.drsel.select_custom_date_range(start, end)

    # --- Properties
    @property
    def start_date(self):
        return self.app.format_date(self._start_date)

    @start_date.setter
    def start_date(self, value):
        date = self.app.parse_date(value)
        if date == self._start_date:
            return
        self._start_date = date
        if date > self._end_date:
            self._end_date = date

    @property
    def end_date(self):
        return self.app.format_date(self._end_date)

    @end_date.setter
    def end_date(self, value):
        date = self.app.parse_date(value)
        if date == self._end_date:
            return
        self._end_date = date
        if date < self._start_date:
            self._start_date = date

