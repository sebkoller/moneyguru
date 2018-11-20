# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from hscommon.gui.selectable_list import GUISelectableList
from hscommon.trans import tr

from ..exception import DuplicateAccountNameError
from ..model.account import AccountType
from ..model.currency import Currencies
from .base import MainWindowPanel, LinkedSelectableList

ACCOUNT_TYPE_DESC = {
    AccountType.Asset: tr("Asset"),
    AccountType.Liability: tr("Liability"),
    AccountType.Income: tr("Income"),
    AccountType.Expense: tr("Expense"),
}

class AccountTypeList(GUISelectableList):
    """A selectable list of all possible :class:`account types <.AccountType>`.

    :param panel: Parent account panel. Has its :attr:`AccountPanel.type` updated when the list
                  selection changes.
    :type panel: :class:`AccountPanel`

    Subclasses :class:`.GUISelectableList`.
    """
    def __init__(self, panel):
        self.panel = panel
        account_types_desc = [ACCOUNT_TYPE_DESC[at] for at in AccountType.InOrder]
        GUISelectableList.__init__(self, account_types_desc)

    def _update_selection(self):
        GUISelectableList._update_selection(self)
        selected_type = AccountType.InOrder[self.selected_index]
        self.panel.type = selected_type

class AccountPanel(MainWindowPanel):
    """Modal dialog letting the user edit the properties of an account.

    Our dialog is loaded up with an :class:`.Account`, which is then written to upon saving.

    Subclasses :class:`.MainWindowPanel`.
    """
    def __init__(self, mainwindow):
        MainWindowPanel.__init__(self, mainwindow)
        self._init_fields()
        self_proxy = weakref.proxy(self)
        self.type_list = AccountTypeList(self_proxy)
        currencies_display = ['%s - %s' % (c, n) for c, n, p in Currencies.all]

        def setfunc(index):
            try:
                self_proxy.currency = Currencies.all[index][0]
            except IndexError:
                pass
        self.currency_list = LinkedSelectableList(items=currencies_display, setfunc=setfunc)

    # --- Override
    def _load(self, account):
        self.document.stop_edition()
        self._init_fields()
        self.name = account.name
        self.type = account.type
        self.currency = account.currency
        self.account_number = account.account_number
        self.inactive = account.inactive
        self.notes = account.notes
        self.type_list.select(AccountType.InOrder.index(self.type))
        for i, (c, n, p) in enumerate(Currencies.all):
            if c == self.currency:
                self.currency_list.select(i)
        self.can_change_currency = not any(e.reconciled for e in account.entries)
        self.account = account # for the save() assert

    def _save(self):
        kwargs = dict(
            name=self.name, type=self.type, account_number=self.account_number,
            inactive=self.inactive, notes=self.notes
        )
        if self.can_change_currency:
            kwargs['currency'] = self.currency
        try:
            self.document.change_accounts([self.account], **kwargs)
        except DuplicateAccountNameError:
            pass

    # --- Private
    def _init_fields(self):
        self.type = AccountType.Asset
        self.currency = None
        self.account_number = ''

