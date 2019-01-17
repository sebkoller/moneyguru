# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import copy

from core.model._ccore import UndoStep
from core.util import extract

GROUP_SWAP_ATTRS = ['name', 'type']
SPLIT_SWAP_ATTRS = ['account', 'amount', 'reconciliation_date']
SCHEDULE_SWAP_ATTRS = ['repeat_type', 'repeat_every', 'stop_date', 'date2exception',
                       'date2globalchange', 'date2instances']
BUDGET_SWAP_ATTRS = SCHEDULE_SWAP_ATTRS + ['account', 'amount']

def swapvalues(first, second, attrs):
    for attr in attrs:
        tmp = getattr(first, attr)
        setattr(first, attr, getattr(second, attr))
        setattr(second, attr, tmp)

class Action:
    """A unit of change that can be undone and redone.

    In here, we store changes that happened to a document in the form of sets containing instances.
    These set's are not documented individually to reduce verbosity, but there's 3 types (``added``,
    ``changed`` and ``deleted``) of sets for each supported instance (``accounts``, ``groups``,
    ``transactions``, ``schedules``, ``budgets``).

    For ``added`` and ``deleted``, it's rather easy. The set contains instances directly. For
    ``change``, it's different. The set contains 2-sized tuples ``(instance, backup)``. Whenever
    we're about to make a change to something, we copy it first and store that backup. Then, when
    we undo our action, we can use our backup.

    To create an action, you can operate on set attributes directly for ``added`` and ``deleted``,
    but you should use convenience method for ``changed``. They perform the copying for you.

    :param str description: A description of the action which will be shown to the user. Example:
                            "Add Transaction", which will show as "Undo Add Transaction".
    """
    def __init__(self, description):
        self.description = description
        self.added_accounts = set()
        self.changed_accounts = set()
        self.deleted_accounts = set()
        self.added_groups = set()
        self.changed_groups = {}
        self.deleted_groups = set()
        self.added_transactions = set()
        self.changed_transactions = {}
        self.deleted_transactions = set()
        self.added_schedules = set()
        self.changed_schedules = {}
        self.deleted_schedules = set()
        self.added_budgets = set()
        self.changed_budgets = {}
        self.deleted_budgets = set()

    def change_accounts(self, accounts):
        """Record imminent changes to ``accounts``."""
        self.changed_accounts |= set(accounts)

    def change_groups(self, groups):
        """Record imminent changes to ``groups``."""
        for g in groups:
            if g not in self.changed_groups:
                self.changed_groups[g] = copy.copy(g)

    def change_schedule(self, schedule):
        """Record imminent changes to ``schedule``."""
        if schedule not in self.changed_schedules:
            self.changed_schedules[schedule] = schedule.replicate()

    def change_budget(self, budget):
        """Record imminent changes to ``budget``."""
        if budget not in self.changed_budgets:
            self.changed_budgets[budget] = budget.replicate()

    def change_transactions(self, transactions, schedules):
        """Record imminent changes to ``transactions``.

        If any of the transactions are a :class:`.Spawn`, also record a change to their related
        schedule.
        """
        spawns, normal = extract(lambda t: t.is_spawn, transactions)
        for t in normal:
            if t not in self.changed_transactions:
                self.changed_transactions[t] = t.replicate()
        for spawn in spawns:
            for schedule in schedules:
                if schedule.contains_ref(spawn.ref):
                    self.change_schedule(schedule)

    def change_entries(self, entries, schedules):
        """Record imminent changes to ``entries``."""
        self.change_transactions({e.transaction for e in entries}, schedules)


class Undoer:
    """Manages undo/redo operation for a document.

    Note: We hold references to all those instance collections passed during initialization rather
    than the :class:`.Document` itself to avoid circular references. But yes, initialisation
    arguments must come straight from document attributes.

    How it works is that it holds a list of :class:`.Action` and a pointer to our current action
    (most of the time, it's the last action). When we undo or redo an action, we use the information
    we has stored in our action and make proper modifications, then move our action index.
    """
    def __init__(self, accounts, groups, transactions, scheduled, budgets):
        self._actions = []
        self._accounts = accounts
        self._groups = groups
        self._transactions = transactions
        self._scheduled = scheduled
        self._budgets = budgets
        self._index = -1
        self._save_point = None

    # --- Private
    def _add_auto_created_accounts(self, transaction):
        for split in transaction.splits:
            if split.account is not None and split.account not in self._accounts:
                split.account = self._accounts.create_from(split.account)

    def _do_adds(self, accounts, groups, transactions, schedules, budgets):
        for group in groups:
            self._groups.append(group)
        for txn in transactions:
            self._transactions.add(txn, True)
            self._add_auto_created_accounts(txn)
        for schedule in schedules:
            self._scheduled.append(schedule)
        for budget in budgets:
            self._budgets.append(budget)

    def _do_changes(self, action):
        for group, old in action.changed_groups.items():
            swapvalues(group, old, GROUP_SWAP_ATTRS)
        for txn, old in action.changed_transactions.items():
            self._remove_auto_created_account(txn)
            newold = txn.replicate()
            txn.copy_from(old)
            old.copy_from(newold)
            self._add_auto_created_accounts(txn)
        for schedule, old in action.changed_schedules.items():
            swapvalues(schedule, old, SCHEDULE_SWAP_ATTRS)
            newold = schedule.ref.replicate()
            schedule.ref.copy_from(old.ref)
            old.ref.copy_from(newold)
        for budget, old in action.changed_budgets.items():
            swapvalues(budget, old, BUDGET_SWAP_ATTRS)

    def _do_deletes(self, accounts, groups, transactions, schedules, budgets):
        for group in groups:
            self._groups.remove(group)
        for txn in transactions:
            self._remove_auto_created_account(txn)
            self._transactions.remove(txn)
        for schedule in schedules:
            self._scheduled.remove(schedule)
        for budget in budgets:
            self._budgets.remove(budget)

    def _remove_auto_created_account(self, transaction):
        for split in transaction.splits:
            account = split.account
            if account is not None:
                entries = self._accounts.entries_for_account(account)
            else:
                entries = []
            # if len(account.entries) == 1, it means that the transactions was last
            if account and account.autocreated and len(entries) == 1:
                self._accounts.remove(account)

    # --- Public
    def can_redo(self):
        """Whether we can redo.

        In other words, whether we have at least one action and that our current action pointer
        isn't pointing on the last one.
        """
        return self._index < -1

    def can_undo(self):
        """Whether we can undo.

        In other words, whether we have at least one action that hasn't been undone already.
        """
        return -self._index <= len(self._actions)

    def clear(self):
        """Clear our action list."""
        self._actions = []

    def undo_description(self):
        """Textual description of the action to be undone next."""
        if self.can_undo():
            return self._actions[self._index].description

    def redo_description(self):
        """Textual description of the action to be redone next."""
        if self.can_redo():
            return self._actions[self._index + 1].description

    def set_save_point(self):
        """Specify at which point we saved last.

        This allows us to determine whether the document should be considered :attr:`modified`.

        Call this method whenever the document is saved.
        """
        self._save_point = self._actions[-1] if self._actions else None

    def record(self, action):
        """Record an action and add it to the list.

        If we're not currently pointing at the end of the list (if we have undone actions before
        recording our new action), discard all actions following the current one before recording
        our new action.

        :param action: Action to be recorded.
        :type action: :class:`Action`
        """
        action.undostep = UndoStep(
            action.added_accounts,
            action.deleted_accounts,
            action.changed_accounts)
        if self._index < -1:
            self._actions = self._actions[:self._index + 1]
        self._actions.append(action)
        self._index = -1

    def undo(self):
        """Undo the next action to be undone.

        If our last action was :meth:`record`, then we undo that action. If it was :meth:`undo`,
        then we undo the action that came before it. If it was :meth:`redo`, then we re-undo that
        action and decrease our pointer to the previous action.

        Make sure you can call this with :meth:`can_undo` first.
        """
        assert self.can_undo()
        action = self._actions[self._index]
        action.undostep.undo(self._accounts)
        self._do_adds(
            action.deleted_accounts, action.deleted_groups, action.deleted_transactions,
            action.deleted_schedules, action.deleted_budgets
        )
        self._do_deletes(
            action.added_accounts, action.added_groups, action.added_transactions,
            action.added_schedules, action.added_budgets
        )
        self._do_changes(action)
        self._index -= 1

    def redo(self):
        """Redo the next action to be redone.

        This can only be performed if we've done :meth:`undo` before. We redo that action and
        increase our pointer to the next action.

        Make sure you can call this with :meth:`can_redo` first.
        """
        assert self.can_redo()
        action = self._actions[self._index + 1]
        action.undostep.redo(self._accounts)
        self._do_adds(
            action.added_accounts, action.added_groups, action.added_transactions,
            action.added_schedules, action.added_budgets
        )
        self._do_deletes(
            action.deleted_accounts, action.deleted_groups, action.deleted_transactions,
            action.deleted_schedules, action.deleted_budgets
        )
        self._do_changes(action)
        self._index += 1

    # --- Properties
    @property
    def modified(self):
        """Whether we can consider our document modified.

        A document is modified if the current action pointer doesn't point to the same action as
        when :meth:`set_save_point` was last called.
        """
        return self._save_point is not self._actions[self._index] if self.can_undo() else self._save_point is not None

