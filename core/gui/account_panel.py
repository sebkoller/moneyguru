# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from core.trans import tr

from ..const import AccountType
from ..model.currency import Currencies
from .base import GUIPanel
from .selectable_list import GUISelectableList, LinkedSelectableList

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

class AccountPanel(GUIPanel):
    """Modal dialog letting the user edit the properties of an account.

    Our dialog is loaded up with an :class:`.Account`, which is then written to upon saving.

    Subclasses :class:`.GUIPanel`.
    """
    def __init__(self, mainwindow):
        GUIPanel.__init__(self, mainwindow)
        self._init_fields()
        self_proxy = weakref.proxy(self)
        self.type_list = AccountTypeList(self_proxy)

        def setfunc(index):
            try:
                self_proxy.currency = Currencies.code_at_index(index)
            except IndexError:
                pass
        self.currency_list = LinkedSelectableList(
            items=Currencies.display_list(), setfunc=setfunc)

    # --- Override
    def _load(self, account):
        self.mainwindow.stop_editing()
        self._init_fields()
        self.name = account.name
        self.type = account.type
        self.currency = account.currency
        self.account_number = account.account_number
        self.inactive = account.inactive
        self.notes = account.notes
        self.type_list.select(AccountType.InOrder.index(self.type))
        try:
            self.currency_list.select(Currencies.index(self.currency))
        except IndexError:
            pass
        entries = self.document.accounts.entries_for_account(account)
        self.can_change_currency = not any(e.reconciled for e in entries)
        self.account = account # for the save() assert

    def _save(self):
        kwargs = dict(
            name=self.name, type=self.type, account_number=self.account_number,
            inactive=self.inactive, notes=self.notes
        )
        if self.can_change_currency:
            kwargs['currency'] = self.currency
        self.document.change_accounts([self.account], **kwargs)
        self.mainwindow.revalidate()

    # --- Private
    def _init_fields(self):
        self.type = AccountType.Asset
        self.currency = None
        self.account_number = ''

