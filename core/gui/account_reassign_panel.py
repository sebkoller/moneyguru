# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr

from ..model.sort import ACCOUNT_SORT_KEY
from .base import GUIPanel
from .selectable_list import GUISelectableList

class AccountReassignPanel(GUIPanel):
    def __init__(self, mainwindow):
        GUIPanel.__init__(self, mainwindow)
        self.account_list = GUISelectableList()

    def _load(self, accounts):
        self.deleted_accounts = set(accounts)
        all_accounts = list(self.document.accounts)
        target_accounts = sorted(
            (a for a in all_accounts if a not in self.deleted_accounts),
            key=ACCOUNT_SORT_KEY)
        target_account_names = [a.name for a in target_accounts]
        target_account_names.insert(0, tr('No Account'))
        self._target_accounts = target_accounts
        self._target_accounts.insert(0, None)
        self.account_list[:] = target_account_names
        self.account_list.select(0)

    def _save(self):
        reassign_to = self._target_accounts[self.account_list.selected_index]
        self.document.delete_accounts(self.deleted_accounts, reassign_to=reassign_to)
        self.mainwindow.revalidate()

