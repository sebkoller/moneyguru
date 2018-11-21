# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from hscommon.trans import tr

from ..const import PaneType
from ..model.currency import Currencies
from .base import BaseView, LinkedSelectableList

class DocPropsView(BaseView):
    VIEW_TYPE = PaneType.DocProps
    INVALIDATING_MESSAGES = {'document_changed'}

    def __init__(self, mainwindow):
        BaseView.__init__(self, mainwindow)
        WEEKDAYS = [
            tr("Monday"),
            tr("Tuesday"),
            tr("Wednesday"),
            tr("Thursday"),
            tr("Friday"),
            tr("Saturday"),
            tr("Sunday"),
        ]

        def setfunc(index):
            self.document.first_weekday = index
        self.first_weekday_list = LinkedSelectableList(items=WEEKDAYS, setfunc=setfunc)

        def setfunc(index):
            self.document.ahead_months = index
        self.ahead_months_list = LinkedSelectableList(items=list(map(str, range(12))), setfunc=setfunc)
        MONTHS = [
            tr("January"),
            tr("February"),
            tr("March"),
            tr("April"),
            tr("May"),
            tr("June"),
            tr("July"),
            tr("August"),
            tr("September"),
            tr("October"),
            tr("November"),
            tr("December"),
        ]

        def setfunc(index):
            self.document.year_start_month = index + 1
        self.year_start_month_list = LinkedSelectableList(items=MONTHS, setfunc=setfunc)
        currencies_display = ['%s - %s' % (c.code, n) for c, n, p in Currencies.all]

        def setfunc(index):
            self.document.default_currency = Currencies.all[index][0].code
        self.currency_list = LinkedSelectableList(items=currencies_display, setfunc=setfunc)

    def _revalidate(self):
        for i, (c, n, p) in enumerate(Currencies.all):
            if c.code == self.document.default_currency:
                self.currency_list.select(i)
        self.first_weekday_list.select(self.document.first_weekday)
        self.ahead_months_list.select(self.document.ahead_months)
        self.year_start_month_list.select(self.document.year_start_month - 1)

    # --- Events
    document_changed = _revalidate
