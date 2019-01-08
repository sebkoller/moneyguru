# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime

from .base import ViewChild
from .table import GUITable, TableWithAmountMixin
from .completable_edit import CompletableEdit

class TransactionSelectionMixin:
    """Mixin class that allows a selection at a certain date to be "remembered" in a view.

    This class operates by assuming that the subclass will override the method
    ``_explicitly_selected_transactions``, return those transactions which were
    explicitly selected by the user.  This selection set has to be "remembered" before
    a refresh of the table is conducted and therefore the selection will have changed.
    """

    def select_transactions(self, transactions):
        selected_indexes = []
        for index, row in enumerate(self):
            if hasattr(row, 'transaction') and row.transaction in transactions:
                selected_indexes.append(index)
        self.selected_indexes = selected_indexes

    # virtual
    @property
    def _explicitly_selected_transactions(self):
        #  for example, this line could be:
        # return self.mainwindow.explicitly_selected_transactions
        return []

    # private
    def _restore_from_explicit_selection(self, refresh_view=True):
        if self._explicitly_selected_transactions:
            self.select_transactions(self._explicitly_selected_transactions)
            if not self.selected_indexes:
                self._select_nearest_date(self._explicitly_selected_transactions[0].date)
            if refresh_view:
                self.view.update_selection()

    def _select_nearest_date(self, target_date):
        # This method assumes that self is sorted by date
        last_delta = datetime.timedelta.max
        for index, row in enumerate(self):
            delta = abs(row._date - target_date)
            if delta > last_delta:
                # The last iteration was the correct one
                self.selected_index = index - 1
                break
            last_delta = delta
        else:
            self.selected_index = len(self) - 1


class TransactionTableBase(GUITable, ViewChild, TransactionSelectionMixin, TableWithAmountMixin):
    """Common superclass for TransactionTable and EntryTable, which share a lot of logic.
    """

    def __init__(self, parent_view):
        GUITable.__init__(self, document=parent_view.document)
        ViewChild.__init__(self, parent_view)
        self.parent_view = parent_view
        self.mainwindow = parent_view.mainwindow
        self.document = self.mainwindow.document
        self.app = self.document.app
        self._invalidated = True
        self.completable_edit = CompletableEdit(parent_view.mainwindow)

    # --- Override
    def _do_restore_view(self):
        self.columns.restore_columns()

    def _is_edited_new(self):
        return self.edited.transaction not in self.document.transactions

    def _restore_selection(self, previous_selection):
        # We do the default selection restore, but if we end up selecting the Total row and there's
        # a row above it, we select it.
        GUITable._restore_selection(self, previous_selection)
        if self.selected_indexes == [len(self)-1] and len(self) > 1:
            self.selected_indexes = [len(self) - 2]

    def _update_selection(self):
        self.mainwindow.explicitly_selected_transactions = self.selected_transactions

    def add(self):
        GUITable.add(self)

    def _revalidate(self):
        self.refresh()
        self._invalidated = False

    def save_edits(self):
        if self.edited is None and len(self.selected_indexes) == 1:
            # normally, with a `None` self.edited, we would do nothing. However,
            # if what we have is a spawn and that it's in the past, we're going
            # to materialize it.
            row = self.selected_row
            if hasattr(row, 'transaction'):
                txn = row.transaction
                if txn.is_spawn and txn.date <= datetime.date.today():
                    self.document.materialize_spawn(txn)
                    self.mainwindow.revalidate()
        super().save_edits()

    def show(self):
        if self._invalidated:
            self._revalidate()
        self._restore_from_explicit_selection()
        self.mainwindow.selected_transactions = self.selected_transactions
        self.view.show_selected_row()

    # --- Protected

    @property
    def _explicitly_selected_transactions(self):
        return self.mainwindow.explicitly_selected_transactions

    # --- Public
    def can_move(self, row_indexes, position):
        if self._sort_descriptor is not None and self._sort_descriptor != ('date', False):
            return False
        if not GUITable.can_move(self, row_indexes, position):
            return False
        if not all(self[index].can_edit() for index in row_indexes):
            return False
        transactions = [self[index].transaction for index in row_indexes]
        before = self[position - 1] if position > 0 else None
        after = self[position] if position < len(self) else None
        # before and after are rows, get the txn if it exists
        before = before.transaction if hasattr(before, 'transaction') else None
        after = after.transaction if hasattr(after, 'transaction') else None
        return self.document.can_move_transactions(transactions, before, after)

    def duplicate_selected(self):
        self.document.duplicate_transactions(self.selected_transactions)
        self.mainwindow.revalidate()

    def move(self, row_indexes, to_index):
        try:
            to_row = self[to_index]
            to_transaction = getattr(to_row, 'transaction', None)
        except IndexError:
            to_transaction = None
        # we can use any from_index, let's use the first
        transactions = [self[index].transaction for index in row_indexes]
        self.document.move_transactions(transactions, to_transaction)
        self.mainwindow.revalidate()

    def move_down(self):
        """Moves the selected entry down one slot if possible"""
        if len(self.selected_indexes) != 1:
            return
        position = self.selected_indexes[-1] + 2
        if self.can_move(self.selected_indexes, position):
            self.move(self.selected_indexes, position)

    def move_up(self):
        """Moves the selected entry up one slot if possible"""
        if len(self.selected_indexes) != 1:
            return
        position = self.selected_indexes[0] - 1
        if self.can_move(self.selected_indexes, position):
            self.move(self.selected_indexes, position)
