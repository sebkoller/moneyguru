# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import weakref

from ..saver.csv import save as save_csv
from ..saver.qif import save as save_qif
from .base import GUIPanel
from .export_account_table import ExportAccountTable

class ExportFormat:
    QIF = 0
    CSV = 1

class ExportPanel(GUIPanel):
    def __init__(self, mainwindow):
        GUIPanel.__init__(self, mainwindow)
        self.account_table = ExportAccountTable(weakref.proxy(self))

    def _load(self, accounts):
        self.accounts = accounts
        self.exported_names = set()
        self.export_all = True
        self.export_format = ExportFormat.QIF
        self.export_path = None
        self.current_daterange_only = False
        self.account_table.refresh()

    def _save(self):
        accounts = self.accounts
        if not self.export_all:
            accounts = [a for a in accounts if a.name in self.exported_names]
        save_func = {
            ExportFormat.QIF: save_qif,
            ExportFormat.CSV: save_csv,
        }[self.export_format]
        if self.current_daterange_only:
            daterange = self.document.date_range
        else:
            daterange = None
        account_pairs = [
            (a, self.document.accounts.entries_for_account(a))
            for a in accounts]
        save_func(self.export_path, account_pairs, daterange=daterange)

    # --- Public
    def is_exported(self, name):
        return name in self.exported_names

    def set_exported(self, name, value):
        if value:
            self.exported_names.add(name)
        else:
            self.exported_names.discard(name)
        self.view.set_export_button_enabled(bool(self._export_all or self.exported_names))

    # --- Properties
    @property
    def export_all(self):
        return self._export_all

    @export_all.setter
    def export_all(self, value):
        self._export_all = value
        self.view.set_table_enabled(not self._export_all)
        self.view.set_export_button_enabled(bool(self._export_all or self.exported_names))

