# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref
from datetime import date

from core.util import allsame, flatten

from ..model.currency import Currencies
from .base import GUIPanel
from .completable_edit import CompletableEdit
from .selectable_list import LinkedSelectableList
from .text_field import TextField

class MassEditTextField(TextField):
    def __init__(self, panel, fieldname):
        TextField.__init__(self)
        self._panel = panel
        self._attrname = '_' + fieldname
        self._enabledname = fieldname + '_enabled'

    def _update(self, newvalue):
        setattr(self._panel, self._attrname, newvalue)
        setattr(self._panel, self._enabledname, True)
        self._panel.view.refresh()


class MassEditDateField(MassEditTextField):
    def _parse(self, text):
        return self._panel.app.parse_date(text)

    def _format(self, value):
        return self._panel.app.format_date(value)


class MassEditAmountField(MassEditTextField):
    def _parse(self, text):
        return self._panel.document.parse_amount(text)

    def _format(self, value):
        return self._panel.document.format_amount(value)


class MassEditionPanel(GUIPanel):
    def __init__(self, mainwindow):
        GUIPanel.__init__(self, mainwindow)
        self_proxy = weakref.proxy(self)
        self.date_field = MassEditDateField(self_proxy, 'date')
        self.description_field = MassEditTextField(self_proxy, 'description')
        self.payee_field = MassEditTextField(self_proxy, 'payee')
        self.checkno_field = MassEditTextField(self_proxy, 'checkno')
        self.from_field = MassEditTextField(self_proxy, 'from')
        self.to_field = MassEditTextField(self_proxy, 'to')
        self.amount_field = MassEditAmountField(self_proxy, 'amount')
        self.completable_edit = CompletableEdit(mainwindow)

        def setfunc(index):
            try:
                currency = Currencies.code_at_index(index)
            except IndexError:
                currency = None
            if currency != self_proxy.currency:
                self_proxy.currency = currency
                self_proxy.currency_enabled = currency is not None
                self_proxy.view.refresh()
        self.currency = None
        self.currency_list = LinkedSelectableList(
            items=Currencies.display_list(), setfunc=setfunc)
        self._init_checkboxes()

    # --- Private
    def _init_checkboxes(self):
        self.date_enabled = False
        self.description_enabled = False
        self.payee_enabled = False
        self.checkno_enabled = False
        self.from_enabled = False
        self.to_enabled = False
        self.amount_enabled = False
        self.currency_enabled = False

    # --- Override
    def _load(self, transactions):
        assert len(transactions) >= 2
        self.can_change_accounts = all(len(t.splits) == 2 for t in transactions)
        self.can_change_amount = all(t.can_set_amount for t in transactions)
        self.date_field.value = date.today()
        self.description_field.text = ''
        self.payee_field.text = ''
        self.checkno_field.text = ''
        self.from_field.text = ''
        self.to_field.text = ''
        self.amount_field.value = 0
        self.currency = None
        first = transactions[0]
        if allsame(t.date for t in transactions):
            self.date_field.value = first.date
        if allsame(t.description for t in transactions):
            self.description_field.text = first.description
        if allsame(t.payee for t in transactions):
            self.payee_field.text = first.payee
        if allsame(t.checkno for t in transactions):
            self.checkno_field.text = first.checkno
        splits = flatten(t.splits for t in transactions)
        splits = [s for s in splits if s.amount]
        if splits and allsame(s.amount.currency_code for s in splits):
            self.currency = splits[0].amount.currency_code
        else:
            self.currency = self.document.default_currency
        try:
            self.currency_list.select(Currencies.index(self.currency))
        except IndexError:
            pass
        if self.can_change_accounts:
            def get_from(t):
                s1, s2 = t.splits
                return s1 if s1.amount <= 0 else s2

            def get_to(t):
                s1, s2 = t.splits
                return s2 if s1.amount <= 0 else s1

            def get_name(split):
                return split.account.name if split.account is not None else ''

            if allsame(get_name(get_from(t)) for t in transactions):
                self.from_field.text = get_name(get_from(first))
            if allsame(get_name(get_to(t)) for t in transactions):
                self.to_field.text = get_name(get_to(first))
        if self.can_change_amount:
            if allsame(t.amount for t in transactions):
                self.amount_field.value = first.amount
        self._init_checkboxes()

    def _save(self):
        transactions = self.mainwindow.selected_transactions
        kw = {}
        if self.date_enabled:
            kw['date'] = self.date_field.value
        if self.description_enabled:
            kw['description'] = self.description_field.text
        if self.payee_enabled:
            kw['payee'] = self.payee_field.text
        if self.checkno_enabled:
            kw['checkno'] = self.checkno_field.text
        if self.from_enabled:
            kw['from_'] = self.from_field.text
        if self.to_enabled:
            kw['to'] = self.to_field.text
        if self.amount_enabled:
            kw['amount'] = self.amount_field.value
        if self.currency_enabled:
            kw['currency'] = self.currency
        if kw:
            self.document.change_transactions(transactions, **kw)
            self.mainwindow.revalidate()

