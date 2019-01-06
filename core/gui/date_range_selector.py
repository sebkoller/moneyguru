# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import weakref

from ..const import DATE_FORMAT_FOR_PREFERENCES
from ..model.date import (
    MonthRange, QuarterRange, YearRange, YearToDateRange, RunningYearRange,
    AllTransactionsRange, CustomDateRange
)
from .base import NoopGUI
from .custom_date_range_panel import CustomDateRangePanel

SELECTED_DATE_RANGE_PREFERENCE = 'SelectedDateRange'
SELECTED_DATE_RANGE_START_PREFERENCE = 'SelectedDateRangeStart'
SELECTED_DATE_RANGE_END_PREFERENCE = 'SelectedDateRangeEnd'

DATE_RANGE_MONTH = 'month'
DATE_RANGE_QUARTER = 'quarter'
DATE_RANGE_YEAR = 'year'
DATE_RANGE_YTD = 'ytd'
DATE_RANGE_RUNNING_YEAR = 'running_year'
DATE_RANGE_ALL_TRANSACTIONS = 'all_transactions'
DATE_RANGE_CUSTOM = 'custom'

class DateRangeSelector:
    def __init__(self, mainwindow):
        self.mainwindow = mainwindow
        self.document = mainwindow.document
        self.app = mainwindow.document.app
        self.view = NoopGUI()
        self._old_date_range = None

    # --- Private
    def _date_range_starting_point(self):
        if self.mainwindow.selected_transactions:
            return self.mainwindow.selected_transactions[0].date
        elif datetime.date.today() in self.document.date_range:
            return datetime.date.today()
        else:
            return self.document.date_range

    # --- Public
    def refresh(self):
        self.view.refresh()
        old = self._old_date_range
        new = self.document.date_range
        self._old_date_range = new
        if old is not None:
            if type(new) == type(old):
                if new.start > old.start:
                    self.view.animate_forward()
                else:
                    self.view.animate_backward()

    def refresh_custom_ranges(self):
        self.view.refresh_custom_ranges()

    def restore_view(self):
        start_date = self.app.get_default(SELECTED_DATE_RANGE_START_PREFERENCE)
        if start_date:
            start_date = datetime.datetime.strptime(start_date, DATE_FORMAT_FOR_PREFERENCES).date()
        end_date = self.app.get_default(SELECTED_DATE_RANGE_END_PREFERENCE)
        if end_date:
            end_date = datetime.datetime.strptime(end_date, DATE_FORMAT_FOR_PREFERENCES).date()
        selected_range = self.app.get_default(SELECTED_DATE_RANGE_PREFERENCE)
        if selected_range == DATE_RANGE_MONTH:
            self.select_month_range(start_date)
        elif selected_range == DATE_RANGE_QUARTER:
            self.select_quarter_range(start_date)
        elif selected_range == DATE_RANGE_YEAR:
            self.select_year_range(start_date)
        elif selected_range == DATE_RANGE_YTD:
            self.select_year_to_date_range()
        elif selected_range == DATE_RANGE_RUNNING_YEAR:
            self.select_running_year_range()
        elif selected_range == DATE_RANGE_CUSTOM and start_date and end_date:
            self.select_custom_date_range(start_date, end_date)
        elif selected_range == DATE_RANGE_ALL_TRANSACTIONS:
            self.select_all_transactions_range()

    def save_custom_range(self, slot, name, start, end):
        # called by the CustomDateRangePanel
        self.app.save_custom_range(slot, name, start, end)
        self.refresh_custom_ranges()

    def save_preferences(self):
        dr = self.document.date_range
        selected_range = DATE_RANGE_MONTH
        if isinstance(dr, QuarterRange):
            selected_range = DATE_RANGE_QUARTER
        elif isinstance(dr, YearRange):
            selected_range = DATE_RANGE_YEAR
        elif isinstance(dr, YearToDateRange):
            selected_range = DATE_RANGE_YTD
        elif isinstance(dr, RunningYearRange):
            selected_range = DATE_RANGE_RUNNING_YEAR
        elif isinstance(dr, AllTransactionsRange):
            selected_range = DATE_RANGE_ALL_TRANSACTIONS
        elif isinstance(dr, CustomDateRange):
            selected_range = DATE_RANGE_CUSTOM
        self.app.set_default(SELECTED_DATE_RANGE_PREFERENCE, selected_range)
        str_start_date = dr.start.strftime(DATE_FORMAT_FOR_PREFERENCES)
        self.app.set_default(SELECTED_DATE_RANGE_START_PREFERENCE, str_start_date)
        str_end_date = dr.end.strftime(DATE_FORMAT_FOR_PREFERENCES)
        self.app.set_default(SELECTED_DATE_RANGE_END_PREFERENCE, str_end_date)

    def select_month_range(self, starting_point=None):
        starting_point = starting_point or self._date_range_starting_point()
        self.set_date_range(MonthRange(starting_point))

    def select_quarter_range(self, starting_point=None):
        starting_point = starting_point or self._date_range_starting_point()
        self.set_date_range(QuarterRange(starting_point))

    def select_year_range(self, starting_point=None):
        starting_point = starting_point or self._date_range_starting_point()
        self.set_date_range(YearRange(
            starting_point,
            year_start_month=self.year_start_month))

    def select_year_to_date_range(self):
        self.set_date_range(YearToDateRange(year_start_month=self.year_start_month))

    def select_running_year_range(self):
        self.set_date_range(RunningYearRange(ahead_months=self.ahead_months))

    def select_all_transactions_range(self):
        if not self.document.transactions:
            return
        first_date = self.document.transactions.first().date
        last_date = self.document.transactions.last().date
        self.set_date_range(AllTransactionsRange(
            first_date=first_date, last_date=last_date,
            ahead_months=self.ahead_months
        ))

    def select_custom_date_range(self, start_date=None, end_date=None):
        if start_date is None:
            panel = CustomDateRangePanel(self)
            panel.view = weakref.proxy(self.mainwindow.view.get_panel_view(panel))
            panel.load()
        else:
            self.set_date_range(CustomDateRange(start_date, end_date, self.app.format_date))

    def select_prev_date_range(self):
        if self.document.date_range.can_navigate:
            self.set_date_range(self.document.date_range.prev())

    def select_next_date_range(self):
        if self.document.date_range.can_navigate:
            self.set_date_range(self.document.date_range.next())

    def select_today_date_range(self):
        if self.document.date_range.can_navigate:
            self.set_date_range(self.document.date_range.around(datetime.date.today()))

    def select_saved_range(self, slot):
        saved_range = self.app.saved_custom_ranges[slot]
        if saved_range:
            self.select_custom_date_range(saved_range.start, saved_range.end)

    def set_date_range(self, new_range):
        prev_range = self.document.date_range
        self.document.date_range = new_range
        self.refresh()
        self.mainwindow.apply_date_range(new_range, prev_range)

    # --- Properties
    @property
    def ahead_months(self):
        return self.document._properties['ahead_months']

    @ahead_months.setter
    def ahead_months(self, value):
        assert 0 <= value <= 11
        if value == self.document._properties['ahead_months']:
            return
        self.document._properties['ahead_months'] = value
        self.document.set_dirty()
        self.set_date_range(self.document.date_range.with_new_args(ahead_months=value))

    @property
    def can_navigate(self):
        return self.document.date_range.can_navigate

    @property
    def custom_range_names(self):
        return [(r.name if r else None) for r in self.app.saved_custom_ranges]

    @property
    def display(self):
        return self.document.date_range.display

    @property
    def year_start_month(self):
        return self.document._properties['year_start_month']

    @year_start_month.setter
    def year_start_month(self, value):
        assert 1 <= value <= 12
        if value == self.document._properties['year_start_month']:
            return
        self.document._properties['year_start_month'] = value
        self.document.set_dirty()
        self.set_date_range(self.document.date_range.with_new_args(year_start_month=value))

