# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
from collections import defaultdict

from core.util import dedupe, first as getfirst
from core.trans import tr

from ..model.date import DateFormat
from .base import GUIObject
from .import_table import ImportTable
from .selectable_list import LinkedSelectableList

DAY = 'day'
MONTH = 'month'
YEAR = 'year'

class SwapType:
    DayMonth = 0
    MonthYear = 1
    DayYear = 2
    DescriptionPayee = 3
    InvertAmount = 4

def last_two_digits(year):
    return year - ((year // 100) * 100)

def swapped_date(date, first, second):
    attrs = {DAY: date.day, MONTH: date.month, YEAR: last_two_digits(date.year)}
    newattrs = {first: attrs[second], second: attrs[first]}
    if YEAR in newattrs:
        newattrs[YEAR] += 2000
    return date.replace(**newattrs)

def swap_format_elements(format, first, second):
    # format is a DateFormat
    swapped = format.copy()
    elems = swapped.elements
    TYPE2CHAR = {DAY: 'd', MONTH: 'M', YEAR: 'y'}
    first_char = TYPE2CHAR[first]
    second_char = TYPE2CHAR[second]
    first_index = [i for i, x in enumerate(elems) if x.startswith(first_char)][0]
    second_index = [i for i, x in enumerate(elems) if x.startswith(second_char)][0]
    elems[first_index], elems[second_index] = elems[second_index], elems[first_index]
    return swapped

class AccountPane:
    def __init__(self, iwin, account, target_account, parsing_date_format):
        self.iwin = iwin
        self.account = account
        self._selected_target = target_account
        self.name = account.name
        entries = iwin.loader.accounts.entries_for_account(account)
        self.count = len(entries)
        self.matches = [] # [[ref, imported]]
        self.parsing_date_format = parsing_date_format
        self.max_day = 31
        self.max_month = 12
        self.max_year = 99 # 2 digits
        self._match_entries()
        self._swap_possibilities = set()
        self._compute_swap_possibilities()

    def _compute_swap_possibilities(self):
        entries = list(self.iwin.loader.accounts.entries_for_account(self.account))
        if not entries:
            return
        self._swap_possibilities = set([(DAY, MONTH), (MONTH, YEAR), (DAY, YEAR)])
        for first, second in self._swap_possibilities.copy():
            for entry in entries:
                try:
                    swapped_date(entry.date, first, second)
                except ValueError:
                    self._swap_possibilities.remove((first, second))
                    break

    def _match_entries(self):
        to_import = list(self.iwin.loader.accounts.entries_for_account(self.account))
        reference2entry = {}
        for entry in (e for e in to_import if e.reference):
            reference2entry[entry.reference] = entry
        self.matches = []
        if self.selected_target is not None:
            entries = self.iwin.document.accounts.entries_for_account(self.selected_target)
            for entry in entries:
                if entry.reference in reference2entry:
                    other = reference2entry[entry.reference]
                    if entry.reconciled:
                        self.iwin.import_table.dont_import.add(other)
                    to_import.remove(other)
                    del reference2entry[entry.reference]
                else:
                    other = None
                if other is not None or not entry.reconciled:
                    self.matches.append([entry, other])
        self.matches += [[None, entry] for entry in to_import]
        self._sort_matches()

    def _sort_matches(self):
        self.matches.sort(key=lambda t: t[0].date if t[0] is not None else t[1].date)

    def bind(self, existing, imported):
        [match1] = [m for m in self.matches if m[0] is existing]
        [match2] = [m for m in self.matches if m[1] is imported]
        assert match1[1] is None
        assert match2[0] is None
        match1[1] = match2[1]
        self.matches.remove(match2)

    def can_swap_date_fields(self, first, second): # 'day', 'month', 'year'
        return (first, second) in self._swap_possibilities or (second, first) in self._swap_possibilities

    def match_entries_by_date_and_amount(self, threshold):
        delta = datetime.timedelta(days=threshold)
        unmatched = (
            to_import for ref, to_import in self.matches if ref is None)
        unmatched_refs = (
            ref for ref, to_import in self.matches if to_import is None)
        amount2refs = defaultdict(list)
        for entry in unmatched_refs:
            amount2refs[entry.amount].append(entry)
        for entry in unmatched:
            if entry.amount not in amount2refs:
                continue
            potentials = amount2refs[entry.amount]
            for ref in potentials:
                if abs(ref.date - entry.date) <= delta:
                    self.bind(ref, entry)
                    potentials.remove(ref)
        self._sort_matches()


    def unbind(self, existing, imported):
        [match] = [m for m in self.matches if m[0] is existing and m[1] is imported]
        match[1] = None
        self.matches.append([None, imported])
        self._sort_matches()

    @property
    def selected_target(self):
        return self._selected_target

    @selected_target.setter
    def selected_target(self, value):
        self._selected_target = value
        self._match_entries()


# This is a modal window that is designed to be re-instantiated on each import
# run. It is shown modally by the UI as soon as its created on the UI side.
class ImportWindow(GUIObject):
    # --- View interface
    # close()
    # close_selected_tab()
    # set_swap_button_enabled(enabled: bool)
    # update_selected_pane()
    # show()
    #

    def __init__(self, mainwindow, target_account=None):
        super().__init__()
        if not hasattr(mainwindow, 'loader'):
            raise ValueError("Nothing to import!")
        self.mainwindow = mainwindow
        self.document = mainwindow.document
        self.app = self.document.app
        self._selected_pane_index = 0
        self._selected_target_index = 0

        def setfunc(index):
            self.view.set_swap_button_enabled(self.can_perform_swap())
        self.swap_type_list = LinkedSelectableList(items=[
            "<placeholder> Day <--> Month",
            "<placeholder> Month <--> Year",
            "<placeholder> Day <--> Year",
            tr("Description <--> Payee"),
            tr("Invert Amounts"),
        ], setfunc=setfunc)
        self.swap_type_list.selected_index = SwapType.DayMonth
        self.panes = []
        self.import_table = ImportTable(self)

        self.loader = self.mainwindow.loader
        self.target_accounts = [
            a for a in self.document.accounts if a.is_balance_sheet_account()]
        self.target_accounts.sort(key=lambda a: a.name.lower())
        accounts = []
        for account in self.loader.accounts:
            if account.is_balance_sheet_account():
                entries = self.loader.accounts.entries_for_account(account)
                if len(entries):
                    new_name = self.document.accounts.new_name(account.name)
                    if new_name != account.name:
                        self.loader.accounts.rename_account(account, new_name)
                    accounts.append(account)
        parsing_date_format = DateFormat.from_sysformat(self.loader.parsing_date_format)
        for account in accounts:
            target = target_account
            if target is None and account.reference:
                target = getfirst(
                    t for t in self.target_accounts if t.reference == account.reference
                )
            self.panes.append(
                AccountPane(self, account, target, parsing_date_format))

    # --- Private
    def _can_swap_date_fields(self, first, second): # 'day', 'month', 'year'
        pane = self.selected_pane
        if pane is None:
            return False
        return pane.can_swap_date_fields(first, second)

    def _invert_amounts(self, apply_to_all):
        if apply_to_all:
            panes = self.panes
        else:
            panes = [self.selected_pane]
        for pane in panes:
            entries = self.loader.accounts.entries_for_account(pane.account)
            txns = dedupe(e.transaction for e in entries)
            for txn in txns:
                for split in txn.splits:
                    split.amount = -split.amount
        self.import_table.refresh()

    def _refresh_target_selection(self):
        if not self.panes:
            return
        target = self.selected_pane.selected_target
        self._selected_target_index = 0
        if target is not None:
            try:
                self._selected_target_index = self.target_accounts.index(target) + 1
            except ValueError:
                pass

    def _refresh_swap_list_items(self):
        if not self.panes:
            return
        items = []
        basefmt = self.selected_pane.parsing_date_format
        for first, second in [(DAY, MONTH), (MONTH, YEAR), (DAY, YEAR)]:
            swapped = swap_format_elements(basefmt, first, second)
            items.append("{} --> {}".format(basefmt.iso_format, swapped.iso_format))
        self.swap_type_list[:3] = items

    def _swap_date_fields(self, first, second, apply_to_all): # 'day', 'month', 'year'
        assert self._can_swap_date_fields(first, second)
        if apply_to_all:
            panes = [p for p in self.panes if p.can_swap_date_fields(first, second)]
        else:
            panes = [self.selected_pane]

        def switch_func(txn):
            txn.date = swapped_date(txn.date, first, second)

        self._swap_fields(panes, switch_func)
        # Now, lets' change the date format on these panes
        for pane in panes:
            basefmt = self.selected_pane.parsing_date_format
            swapped = swap_format_elements(basefmt, first, second)
            pane.parsing_date_format = swapped
            pane._sort_matches()
        self.import_table.refresh()
        self._refresh_swap_list_items()

    def _swap_description_payee(self, apply_to_all):
        if apply_to_all:
            panes = self.panes
        else:
            panes = [self.selected_pane]

        def switch_func(txn):
            txn.description, txn.payee = txn.payee, txn.description

        self._swap_fields(panes, switch_func)

    def _swap_fields(self, panes, switch_func):
        seen = set()
        for pane in panes:
            entries = self.loader.accounts.entries_for_account(pane.account)
            txns = dedupe(e.transaction for e in entries)
            for txn in txns:
                if txn.affected_accounts() & seen:
                    # We've already swapped this txn in a previous pane.
                    continue
                switch_func(txn)
            seen.add(pane.account)
        self.import_table.refresh()

    def _update_selected_pane(self):
        self.import_table.refresh()
        self._refresh_swap_list_items()
        self.view.update_selected_pane()
        self.view.set_swap_button_enabled(self.can_perform_swap())

    # --- Override
    def _view_updated(self):
        if self.document.can_restore_from_prefs():
            self.restore_view()
        # XXX Should replace by _update_selected_pane()?
        self._refresh_target_selection()
        self._refresh_swap_list_items()
        self.import_table.refresh()

    # --- Public
    def can_perform_swap(self):
        index = self.swap_type_list.selected_index
        if index == SwapType.DayMonth:
            return self._can_swap_date_fields(DAY, MONTH)
        elif index == SwapType.MonthYear:
            return self._can_swap_date_fields(MONTH, YEAR)
        elif index == SwapType.DayYear:
            return self._can_swap_date_fields(DAY, YEAR)
        else:
            return True

    def close_pane(self, index):
        was_selected = index == self.selected_pane_index
        del self.panes[index]
        if not self.panes:
            self.view.close()
            return
        self._selected_pane_index = min(self._selected_pane_index, len(self.panes) - 1)
        if was_selected:
            self._update_selected_pane()


    def import_selected_pane(self):
        pane = self.selected_pane
        matches = pane.matches
        matches = [
            (e, ref) for ref, e in matches
            if e is not None and e not in self.import_table.dont_import]
        if pane.selected_target is not None:
            # We import in an existing account, adjust all the transactions accordingly
            target_account = pane.selected_target
        else:
            target_account = None
        self.document.import_entries(target_account, pane.account, matches)
        self.mainwindow.revalidate()
        self.close_pane(self.selected_pane_index)
        self.view.close_selected_tab()

    def match_entries_by_date_and_amount(self, threshold):
        self.selected_pane.match_entries_by_date_and_amount(threshold)
        self.import_table.refresh()

    def perform_swap(self, apply_to_all=False):
        index = self.swap_type_list.selected_index
        if index == SwapType.DayMonth:
            self._swap_date_fields(DAY, MONTH, apply_to_all=apply_to_all)
        elif index == SwapType.MonthYear:
            self._swap_date_fields(MONTH, YEAR, apply_to_all=apply_to_all)
        elif index == SwapType.DayYear:
            self._swap_date_fields(DAY, YEAR, apply_to_all=apply_to_all)
        elif index == SwapType.DescriptionPayee:
            self._swap_description_payee(apply_to_all=apply_to_all)
        elif index == SwapType.InvertAmount:
            self._invert_amounts(apply_to_all=apply_to_all)

    def restore_view(self):
        self.import_table.columns.restore_columns()

    # --- Properties
    @property
    def selected_pane(self):
        return self.panes[self.selected_pane_index] if self.panes else None

    @property
    def selected_pane_index(self):
        return self._selected_pane_index

    @selected_pane_index.setter
    def selected_pane_index(self, value):
        if value >= len(self.panes):
            return
        self._selected_pane_index = value
        self._refresh_target_selection()
        self._update_selected_pane()

    @property
    def selected_target_account(self):
        return self.selected_pane.selected_target

    @property
    def selected_target_account_index(self):
        return self._selected_target_index

    @selected_target_account_index.setter
    def selected_target_account_index(self, value):
        target = self.target_accounts[value - 1] if value > 0 else None
        self.selected_pane.selected_target = target
        self._selected_target_index = value
        self.import_table.refresh()

    @property
    def target_account_names(self):
        return [tr('< New Account >')] + [a.name for a in self.target_accounts]
