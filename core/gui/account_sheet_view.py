# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from .base import BaseView
from .account_panel import AccountPanel
from .account_reassign_panel import AccountReassignPanel

class AccountSheetView(BaseView):
    SAVENAME = ''
    # Set self.sheet, self.graph and self.pie in subclasses init

    # --- Overrides
    def _revalidate(self):
        super()._revalidate()
        self.sheet.refresh()
        self.graph._revalidate()
        self.pie._revalidate()

    def apply_date_range(self, new_date_range, prev_date_range):
        self._revalidate()

    def restore_subviews_size(self):
        if self.graph.view_size[1]:
            # Was already restored
            return
        prefname = '{}.GraphHeight'.format(self.SAVENAME)
        self.graph_height_to_restore = self.document.get_default(prefname, 0)
        prefname = '{}.PieWidth'.format(self.SAVENAME)
        self.pie_width_to_restore = self.document.get_default(prefname, 0)

    def restore_view(self):
        super().restore_view()
        self.sheet.restore_view()

    def save_preferences(self):
        self.sheet.save_preferences()
        height = self.graph.view_size[1]
        # It's possible that set_view_size() has never been called. In this case, we have (0, 0).
        if height:
            prefname = '{}.GraphHeight'.format(self.SAVENAME)
            self.document.set_default(prefname, height)
        width = self.pie.view_size[0]
        if width:
            prefname = '{}.PieWidth'.format(self.SAVENAME)
            self.document.set_default(prefname, width)

    def toggle_accounts_exclusion(self, accounts):
        self.document.toggle_accounts_exclusion(accounts)
        self._revalidate()

    def update_visibility(self):
        self.view.update_visibility()

    # --- Public
    def collapse_group(self, group):
        group.expanded = False
        self.pie._revalidate()

    def delete_item(self):
        self.sheet.delete()

    def edit_item(self):
        selected_account = self.sheet.selected_account
        if selected_account is not None:
            account_panel = AccountPanel(self.mainwindow)
            account_panel.view = weakref.proxy(self.view.get_panel_view(account_panel))
            account_panel.load(selected_account)
            return account_panel

    def expand_group(self, group):
        group.expanded = True
        self.pie._revalidate()

    def get_account_reassign_panel(self):
        panel = AccountReassignPanel(self.mainwindow)
        panel.view = weakref.proxy(self.view.get_panel_view(panel))
        return panel

    def new_item(self):
        self.sheet.add_account()

    def new_group(self):
        self.sheet.add_account_group()

    def show(self):
        super().show()
        self.view.update_visibility()

    def show_account(self):
        self.sheet.show_selected_account()

    def stop_editing(self):
        self.sheet.cancel_edits()
