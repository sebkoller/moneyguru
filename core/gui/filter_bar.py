# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html


from ..const import FilterType
from .base import GUIObject

class FilterBar(GUIObject):
    def __init__(self, parent_view):
        GUIObject.__init__(self)
        self.mainwindow = parent_view.mainwindow

    # --- Public
    def refresh(self):
        self.view.refresh()

    # --- Properties
    @property
    def filter_type(self):
        return self.mainwindow.filter_type

    @filter_type.setter
    def filter_type(self, value):
        self.mainwindow.filter_type = value


class EntryFilterBar(FilterBar): # disables buttons
    def __init__(self, account_view):
        FilterBar.__init__(self, account_view)
        self._account = account_view.account

    # --- Override
    def _view_updated(self):
        if self._account.is_income_statement_account():
            self.view.disable_transfers()
        else:
            self.view.enable_transfers()

    def refresh(self):
        FilterBar.refresh(self)
        if self._account.is_income_statement_account() and self.filter_type is FilterType.Transfer:
            self.filter_type = None

