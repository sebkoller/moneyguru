# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import time
import uuid
import logging
import os
import os.path as op
from functools import wraps

from core.util import nonone, allsame, dedupe, extract, first, flatten
from core.trans import tr

from .const import NOEDIT
from .exception import FileFormatError, OperationAborted
from .gui.base import GUIObject
from .loader import native
from .model._ccore import AccountList, Entry, TransactionList
from .model.account import Group, GroupList, AccountType
from .model.amount import parse_amount, format_amount
from .model.currency import Currencies
from .model.budget import BudgetList
from .model.date import YearRange
from .model.oven import Oven
from .model.undo import Undoer, Action
from .model.recurrence import find_schedule_of_ref
from .saver.native import save as save_native

EXCLUDED_ACCOUNTS_PREFERENCE = 'ExcludedAccounts'

class ScheduleScope:
    Local = 0
    Global = 1
    Cancel = 2

AUTOSAVE_BUFFER_COUNT = 10 # Number of autosave files that will be kept in the cache.

def handle_abort(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except OperationAborted:
            pass

    return wrapper

class Document(GUIObject):
    """Manages everything (including views) about an opened document.

    If there's one core class in moneyGuru, this is it. It represents a new or opened document and
    holds all model instances associated to it (accounts, transactions, etc.). The ``Document`` is
    also responsible for notifying all gui instances of changes. While it's OK for GUI instances to
    directly access models (through :attr:`transactions` and :attr:`accounts`, for example), any
    modification to those models have to go through ``Document``'s public methods.

    Another important role of the ``Document`` is to manage undo points. For undo to work properly,
    every mutative action must be properly recorded, and that's what the ``Document`` does.

    When calling methods that take "hard values" (dates, descriptions, etc..), it is expected that
    these values have already been parsed (it's the role of the GUI instances to parse data). So
    dates are ``datetime.date`` instances, amounts are :class:`Amount` instances, indexes are
    ``int``.
    """

    def __init__(self, app):
        GUIObject.__init__(self)
        self.app = app
        self._properties = {
            'default_currency': self.app._default_currency,
            'first_weekday': 0,
            'ahead_months': 3,
            'year_start_month': 1,
        }
        #: :class:`.AccountList` containing all accounts of the document.
        self.accounts = AccountList(self.default_currency)
        #: :class:`.TransactionList` containing all transactions of the document.
        self.transactions = TransactionList()
        # I did not manage to create a repeatable test for it, but self.schedules has to be
        # an ordered collection because the order in which the spawns are created must stay the
        # same
        self.schedules = []
        self.budgets = BudgetList()
        self.oven = Oven(self.accounts, self.transactions, self.schedules, self.budgets)
        self.step = 1
        #: Set of accounts that are currently in "excluded" state.
        self.excluded_accounts = set()
        #: :class:`.GroupList` containing all account groups of the document.
        self.groups = GroupList()
        self._undoer = Undoer(self.accounts, self.groups, self.transactions, self.schedules, self.budgets)
        self._date_range = YearRange(datetime.date.today())
        self._document_id = None
        self._dirty_flag = False

    # --- Private
    def _add_transactions(self, transactions):
        if not transactions:
            return
        for txn in transactions:
            self.transactions.add(txn)
        min_date = min(t.date for t in transactions)
        self._cook(from_date=min_date)

    def _autosave(self):
        existing_names = [name for name in os.listdir(self.app.cache_path) if name.startswith('autosave')]
        existing_names.sort()
        timestamp = int(time.time())
        autosave_name = 'autosave{0}.moneyguru'.format(timestamp)
        while autosave_name in existing_names:
            timestamp += 1
            autosave_name = 'autosave{0}.moneyguru'.format(timestamp)
        self.save_to_xml(op.join(self.app.cache_path, autosave_name), autosave=True)
        if len(existing_names) >= AUTOSAVE_BUFFER_COUNT:
            os.remove(op.join(self.app.cache_path, existing_names[0]))

    def _change_transaction(self, transaction, global_scope=False, **kwargs):
        date = kwargs.get('date', NOEDIT)
        date_changed = date is not NOEDIT and date != transaction.date
        kws = {k: v for k, v in kwargs.items() if v is not NOEDIT}
        transaction.change(**kws)
        if transaction.is_spawn:
            schedule = find_schedule_of_ref(transaction.ref, self.schedules)
            assert schedule is not None
            if global_scope:
                schedule.change_globally(transaction)
            else:
                schedule.delete(transaction)
                materialized = transaction.materialize()
                self.transactions.add(materialized)
        else:
            if transaction not in self.transactions:
                self.transactions.add(transaction)
            elif date_changed:
                self.transactions.move_last(transaction)
        self.transactions.clear_cache()

    def _cook(self, from_date=None):
        self.oven.cook(from_date=from_date, until_date=self.date_range.end)
        # Whenever we cook, we touch. That saves us some touch() repetitions.
        self.touch()

    def _get_action_from_changed_transactions(self, transactions, global_scope=False):
        if len(transactions) == 1 and not transactions[0].is_spawn \
                and transactions[0] not in self.transactions:
            action = Action(tr('Add transaction'))
            action.added_transactions.add(transactions[0])
        else:
            action = Action(tr('Change transaction'))
            action.change_transactions(transactions, self.schedules)
        if global_scope:
            spawns, txns = extract(lambda x: x.is_spawn, transactions)
            action.change_transactions(spawns, self.schedules)
        return action

    def _query_for_scope_if_needed(self, transactions):
        """Queries the UI for change scope if there's any Spawn among transactions.

        Returns whether the chosen scope is global
        Raises OperationAborted if the user cancels the operation.
        """
        if any(txn.is_spawn for txn in transactions):
            scope = self.view.query_for_schedule_scope()
            if scope == ScheduleScope.Cancel:
                raise OperationAborted()
            return scope == ScheduleScope.Global
        else:
            return False

    def _reconcile_spawn_split(self, entry, reconciliation_date):
        # returns a reference to the corresponding materialized split
        schedule = find_schedule_of_ref(entry.transaction.ref, self.schedules)
        assert schedule is not None
        schedule.delete(entry.transaction)
        materialized = entry.transaction.materialize()
        self.transactions.add(materialized)
        split_index = entry.transaction.splits.index(entry.split)
        materialized_split = materialized.splits[split_index]
        materialized_split.reconciliation_date = reconciliation_date
        return materialized, materialized_split

    def _restore_preferences_after_load(self):
        # some preference need the file loaded before attempting a restore
        logging.debug('restore_preferences_after_load() beginning')
        excluded_account_names = set(nonone(self.get_default(EXCLUDED_ACCOUNTS_PREFERENCE), []))
        self.excluded_accounts = {a for a in self.accounts if a.name in excluded_account_names}

    def _save_preferences(self):
        excluded_account_names = [a.name for a in self.excluded_accounts]
        self.set_default(EXCLUDED_ACCOUNTS_PREFERENCE, excluded_account_names)

    # --- Account
    def change_accounts(
            self, accounts, name=NOEDIT, type=NOEDIT, currency=NOEDIT, group=NOEDIT,
            account_number=NOEDIT, inactive=NOEDIT, notes=NOEDIT):
        """Properly sets properties for ``accounts``.

        Sets ``accounts``' properties in a proper manner. Attributes
        corresponding to arguments set to ``NOEDIT`` will not be touched.

        :param accounts: List of :class:`.Account` to be changed.
        :param name: ``str``
        :param type: :class:`.AccountType`
        :param currency: :class:`.Currency`
        :param group: :class:`.Group`
        :param account_number: ``str``
        :param inactive: ``bool``
        :param notes: ``str``
        """
        assert all(a is not None for a in accounts)
        # Check for name clash
        for account in accounts:
            if name is not NOEDIT and name:
                other = self.accounts.find(name)
                if (other is not None) and (other != account):
                    return False
        action = Action(tr('Change account'))
        action.change_accounts(accounts)
        self._undoer.record(action)
        for account in accounts:
            kwargs = {}
            if name is not NOEDIT and name:
                self.accounts.rename_account(account, name.strip())
            if (type is not NOEDIT) and (type != account.type):
                kwargs.update({'type': type, 'groupname': None})
            if currency is not NOEDIT:
                entries = self.accounts.entries_for_account(account)
                assert not any(e.reconciled for e in entries)
                kwargs['currency'] = currency
            if group is not NOEDIT:
                kwargs['groupname'] = group.name if group else None
            if account_number is not NOEDIT:
                kwargs['account_number'] = account_number
            if inactive is not NOEDIT:
                kwargs['inactive'] = inactive
            if notes is not NOEDIT:
                kwargs['notes'] = notes
            if kwargs:
                account.change(**kwargs)
        self._cook()
        self.transactions.clear_cache()
        return True

    def delete_accounts(self, accounts, reassign_to=None):
        """Removes ``accounts`` from the document.

        If the account has entries assigned to it, these entries will be reassigned to the
        ``reassign_to`` account.

        :param accounts: List of :class:`.Account` to be removed.
        :param accounts: :class:`.Account` to use for reassignment.
        """
        # Recording the "Remove account" action into the Undoer is quite something...
        action = Action(tr('Remove account'))
        accounts = set(accounts)
        action.deleted_accounts |= accounts
        all_entries = flatten(self.accounts.entries_for_account(a) for a in accounts)
        if reassign_to is None:
            transactions = {e.transaction for e in all_entries if not e.transaction.is_spawn}
            transactions = {t for t in transactions if not t.affected_accounts() - accounts}
            action.deleted_transactions |= transactions
        action.change_entries(all_entries, self.schedules)
        affected_schedules = [s for s in self.schedules if accounts & s.affected_accounts()]
        for schedule in affected_schedules:
            action.change_schedule(schedule)
        for account in accounts:
            affected_budgets = [b for b in self.budgets if b.account == account or b.target == account]
            if account.is_income_statement_account() and reassign_to is None:
                action.deleted_budgets |= set(affected_budgets)
            else:
                for budget in affected_budgets:
                    action.change_budget(budget)
        self._undoer.record(action)
        for account in accounts:
            self.transactions.reassign_account(account, reassign_to)
            for schedule in affected_schedules:
                schedule.reassign_account(account, reassign_to)
            for budget in affected_budgets:
                if budget.account == account:
                    if reassign_to is None:
                        self.budgets.remove(budget)
                    else:
                        budget.account = reassign_to
                elif budget.target == account:
                    budget.target = reassign_to
                budget.reset_spawn_cache()
            self.accounts.remove(account)
        self._cook()

    def new_account(self, type, group):
        """Create a new account in the document.

        Creates a new account of type ``type``, within the ``group`` (which can be ``None`` to
        indicate no group). The new account will have a unique name based on the string
        "New Account" (if it exists already, a unique number will be appended to it). Once created,
        the account is added to the account list.

        :param type: :class:`.AccountType`
        :param group: :class:`.Group`
        :rtype: :class:`.Account`
        """
        name = self.accounts.new_name(tr('New account'))
        account = self.accounts.create(name, self.default_currency, type)
        if group:
            account.change(groupname=group.name)
        action = Action(tr('Add account'))
        action.added_accounts.add(account)
        self._undoer.record(action)
        self.touch()
        return account

    def toggle_accounts_exclusion(self, accounts):
        """Toggles "excluded" state for ``accounts``.

        If the current excluded state for ``accounts`` is not homogenous, we set all non-excluded
        accounts as excluded and leave excluded accounts in their current state.

        :param accounts: a ``set`` of :class:`.Account`
        """
        if accounts <= self.excluded_accounts: # all accounts are already excluded. re-include all
            self.excluded_accounts -= accounts
        else:
            self.excluded_accounts |= accounts

    # --- Group
    def change_group(self, group, name=NOEDIT):
        """Properly sets properties for ``group``.

        Sets ``group``'s properties in a proper manner.
        Attributes corresponding to arguments set to ``NOEDIT`` will not be touched.

        :param group: :class:`.Group` to be changed
        :param name: ``str``
        """
        assert group is not None
        action = Action(tr('Change group'))
        action.change_groups([group])
        if name is not NOEDIT:
            oldname = group.name
            other = self.groups.find(name, group.type)
            if (other is not None) and (other is not group):
                return False
            group.name = name
            for account in self.accounts:
                if account.groupname == oldname:
                    account.groupname = name
        self._undoer.record(action)
        self.touch()
        return True

    def delete_groups(self, groups):
        """Removes ``groups`` from the document.

        Removes ``groups`` from the group list. All accounts
        belonging to the deleted group have their :attr:`.Account.group` attribute set to ``None``.

        :param groups: list of :class:`.Group`
        """
        groups = set(groups)
        groupnames = {g.name for g in groups}
        accounts = [a for a in self.accounts if a.groupname in groupnames]
        action = Action(tr('Remove group'))
        action.deleted_groups |= groups
        action.change_accounts(accounts)
        self._undoer.record(action)
        for group in groups:
            self.groups.remove(group)
        for account in accounts:
            account.change(groupname=None)
        self.touch()

    def new_group(self, type):
        """Creates a new group of type ``type``.

        The new group will have a unique name based on the string "New Group" (if it exists, a
        unique number will be appended to it). Once created, the group is added to the group list.

        :param type: :class:`.AccountType`
        :rtype: :class:`.Group`
        """
        name = self.groups.new_name(tr('New group'), type)
        group = Group(name, type)
        action = Action(tr('Add group'))
        action.added_groups.add(group)
        self._undoer.record(action)
        self.groups.append(group)
        self.touch()
        return group

    # --- Transaction
    def can_move_transactions(self, transactions, before, after):
        """Returns whether ``transactions`` can be be moved (re-ordered).

        Transactions can only be moved when all transactions are of the same date, and that the date
        of those transaction is between the date of ``before`` and ``after``. When ``before`` or
        ``after`` is ``None``, it means that it's the end or beginning of the list.

        :param transactions: a collection of :class:`Transaction`
        :param before: :class:`Transaction`
        :param after: :class:`Transaction`
        :rtype: ``bool``
        """
        assert transactions
        if any(txn.is_spawn for txn in transactions):
            return False
        if not allsame(txn.date for txn in transactions):
            return False
        from_date = transactions[0].date
        before_date = before.date if before else None
        after_date = after.date if after else None
        return from_date in (before_date, after_date)

    @handle_abort
    def change_transaction(self, original, new):
        """Changes the attributes of ``original`` so that they match those of ``new``.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param original: :class:`.Transaction`
        :param new: :class:`.Transaction`, a modified copy of ``original``.
        """
        global_scope = self._query_for_scope_if_needed([original])
        action = Action(tr('Change transaction'))
        action.change_transactions([original], self.schedules)
        self._undoer.record(action)
        # don't forget that account up here is an external instance. Even if an account of
        # the same name exists in self.accounts, it's not gonna be the same instance.
        for split in new.splits:
            if split.account is not None:
                split.account = self.accounts.find(split.account.name, split.account.type)
        original.change(splits=new.splits)
        min_date = min(original.date, new.date)
        self._change_transaction(
            original, date=new.date, description=new.description,
            payee=new.payee, checkno=new.checkno, notes=new.notes, global_scope=global_scope
        )
        self._cook(from_date=min_date)
        self.accounts.clean_empty_categories()
        self.date_range = self.date_range.around(original.date)

    @handle_abort
    def change_transactions(
            self, transactions, date=NOEDIT, description=NOEDIT, payee=NOEDIT, checkno=NOEDIT,
            from_=NOEDIT, to=NOEDIT, amount=NOEDIT, currency=NOEDIT):
        """Properly sets properties for ``transactions``.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param date: ``datetime.date``
        :param description: ``str``
        :param payee: ``str``
        :param checkno: ``str``
        :param from_: ``str`` (account name)
        :param to: ``str`` (account name)
        :param amount: :class:`.Amount`
        :param currency: :class:`.Currency`
        """
        if len(transactions) == 1:
            global_scope = self._query_for_scope_if_needed(transactions)
        else:
            global_scope = False
        action = self._get_action_from_changed_transactions(transactions, global_scope)
        self._undoer.record(action)
        if from_ is not NOEDIT:
            from_ = self.accounts.find(from_, AccountType.Income) if from_ else None
        if to is not NOEDIT:
            to = self.accounts.find(to, AccountType.Expense) if to else None
        if date is not NOEDIT and amount is not NOEDIT and amount != 0:
            currencies_to_ensure = [amount.currency_code, self.default_currency]
            Currencies.get_rates_db().ensure_rates(date, currencies_to_ensure)

        min_date = date if date is not NOEDIT else datetime.date.max
        for transaction in transactions:
            min_date = min(min_date, transaction.date)
            self._change_transaction(
                transaction, date=date, description=description, payee=payee, checkno=checkno,
                from_=from_, to=to, amount=amount, currency=currency, global_scope=global_scope
            )
        self._cook(from_date=min_date)
        self.accounts.clean_empty_categories()
        self.date_range = self.date_range.around(transactions[-1].date)

    @handle_abort
    def delete_transactions(self, transactions, from_account=None):
        """Removes every transaction in ``transactions`` from the document.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param transactions: a collection of :class:`.Transaction`.
        :param from_account: the :class:`.Account` from which the operation takes place, if any.
        """
        action = Action(tr('Remove transaction'))
        spawns, txns = extract(lambda x: x.is_spawn, transactions)
        global_scope = self._query_for_scope_if_needed(spawns)
        action.change_transactions(spawns, self.schedules)
        action.deleted_transactions |= set(txns)
        self._undoer.record(action)
        for txn in transactions:
            if txn.is_spawn:
                schedule = find_schedule_of_ref(txn.ref, self.schedules)
                assert schedule is not None
                if global_scope:
                    schedule.stop_before(txn)
                else:
                    schedule.delete(txn)
            else:
                self.transactions.remove(txn)
        min_date = min(t.date for t in transactions)
        self._cook(from_date=min_date)
        self.accounts.clean_empty_categories(from_account)

    def duplicate_transactions(self, transactions):
        """Create copies of ``transactions`` in the document.

        Adds undo recording and UI triggers.

        :param transactions: a collection of :class:`.Transaction` to duplicate.
        """
        if not transactions:
            return
        action = Action(tr('Duplicate transactions'))
        duplicated = [txn.replicate() for txn in transactions]
        action.added_transactions |= set(duplicated)
        self._undoer.record(action)
        self._add_transactions(duplicated)

    def materialize_spawn(self, spawn):
        assert spawn.is_spawn
        schedule = find_schedule_of_ref(spawn.ref, self.schedules)
        assert schedule is not None
        action = Action(tr('Materialize transaction'))
        action.change_schedule(schedule)
        schedule.delete(spawn)
        materialized = spawn.materialize()
        action.added_transactions |= {materialized}
        self._undoer.record(action)
        self.transactions.add(materialized)
        self._cook(from_date=materialized.date)

    def move_transactions(self, transactions, to_transaction):
        """Re-orders ``transactions`` so that they are right before ``to_transaction``.

        Adds undo recording and UI triggers.

        :param transactions: a collection of :class:`.Transaction` to move.
        :param to_transaction: target :class:`.Transaction` to move to.
        """
        affected = set(transactions)
        affected_date = transactions[0].date
        affected |= set(self.transactions.transactions_at_date(affected_date))
        action = Action(tr('Move transaction'))
        action.change_transactions(affected, self.schedules)
        self._undoer.record(action)
        for transaction in transactions:
            self.transactions.move_before(transaction, to_transaction)
        self._cook()

    # --- Entry
    @handle_abort
    def change_entry(
            self, entry, date=NOEDIT, reconciliation_date=NOEDIT, description=NOEDIT, payee=NOEDIT,
            checkno=NOEDIT, transfer=NOEDIT, amount=NOEDIT):
        """Properly sets properties for ``entry``.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param entry: :class:`.Entry`
        :param date: ``datetime.date``
        :param reconciliation_date: ``datetime.date``
        :param description: ``str``
        :param payee: ``str``
        :param checkno: ``str``
        :param transfer: ``str`` (name of account)
        :param amount: :class:`.Amount`
        """
        assert entry is not None
        if date is not NOEDIT and amount is not NOEDIT and amount != 0:
            Currencies.get_rates_db().ensure_rates(date, [amount.currency_code, entry.account.currency])
        if reconciliation_date is NOEDIT:
            global_scope = self._query_for_scope_if_needed([entry.transaction])
        else:
            global_scope = False # It doesn't make sense to set a reconciliation date globally
        action = self._get_action_from_changed_transactions([entry.transaction], global_scope)
        self._undoer.record(action)
        if reconciliation_date is not NOEDIT and entry.transaction.is_spawn:
            newtxn, newsplit = self._reconcile_spawn_split(entry, reconciliation_date)
            entry = Entry(newsplit, newtxn)
            action.added_transactions.add(newtxn)
        candidate_dates = [entry.date, date, reconciliation_date, entry.reconciliation_date]
        min_date = min(d for d in candidate_dates if d is not NOEDIT and d is not None)
        if reconciliation_date is not NOEDIT:
            entry.split.reconciliation_date = reconciliation_date
        if (amount is not NOEDIT) and (len(entry.splits) == 1):
            entry.change_amount(amount)
        if (transfer is not NOEDIT) and (len(entry.splits) == 1) and (transfer != entry.transfer):
            auto_create_type = AccountType.Expense if entry.amount < 0 else AccountType.Income
            transfer_account = self.accounts.find(transfer, auto_create_type) if transfer else None
            entry.splits[0].account = transfer_account
        self._change_transaction(
            entry.transaction, date=date, description=description,
            payee=payee, checkno=checkno, global_scope=global_scope
        )
        self._cook(from_date=min_date)
        self.accounts.clean_empty_categories()
        self.date_range = self.date_range.around(entry.date)

    def delete_entries(self, entries):
        """Remove transactions in which ``entries`` belong from the document's transaction list.

        :param entries: list of :class:`.Entry`
        """
        from_account = first(entries).account
        transactions = dedupe(e.transaction for e in entries)
        self.delete_transactions(transactions, from_account=from_account)

    def toggle_entries_reconciled(self, entries):
        """Toggle the reconcile flag of `entries`.

        Sets the ``reconciliation_date`` to entries' date, or unset it when turning the flag off.

        :param entries: list of :class:`.Entry`
        """
        if not entries:
            return
        all_reconciled = not entries or all(entry.reconciled for entry in entries)
        newvalue = not all_reconciled
        action = Action(tr('Change reconciliation'))
        action.change_entries(entries, self.schedules)
        min_date = min(entry.date for entry in entries)
        spawns, entries = extract(lambda e: e.transaction.is_spawn, entries)
        action.change_transactions({e.transaction for e in spawns}, self.schedules)
        self._undoer.record(action)
        if newvalue:
            for entry in entries:
                entry.split.reconciliation_date = entry.transaction.date
            for spawn in spawns:
                # XXX update transaction selection
                newtxn, newsplit = self._reconcile_spawn_split(
                    spawn, spawn.transaction.date)
                action.added_transactions.add(newtxn)
        else:
            for entry in entries:
                entry.split.reconciliation_date = None
        self._cook(from_date=min_date)

    # --- Budget
    def budgeted_amount(self, date_range, filter_excluded=True):
        """Returns the amount budgeted for **all** budgets

        The amount is pro-rated according to ``date_range``.

        If ``filter_excluded`` is true, we ignore accounts in "excluded" state.

        :param date_range: ``datetime.date``
        :param filter_excluded: ``bool``
        :rtype: :class:`.Amount`
        """
        budgets = self.budgets[:]
        currency = self.default_currency
        if filter_excluded:
            # we must remove any budget touching an excluded account.
            is_not_excluded = lambda b: (b.account not in self.excluded_accounts)
            budgets = list(filter(is_not_excluded, budgets))
        if not budgets:
            return 0
        budgeted_amount = sum(-b.amount_for_date_range(date_range, currency=currency) for b in budgets)
        return budgeted_amount

    def change_budget(self, original, new):
        """Changes the attributes of ``original`` so that they match those of ``new``.

        This is used by the :class:`.BudgetPanel`, and ``new`` is originally a copy of ``original``
        which has been changed.

        :param original: :class:`.Budget`
        :param new: :class:`.Budget`
        """
        if original in self.budgets:
            action = Action(tr('Change Budget'))
            action.change_budget(original)
        else:
            action = Action(tr('Add Budget'))
            action.added_budgets.add(original)
        self._undoer.record(action)
        min_date = min(original.start_date, new.start_date)
        original.start_date = new.start_date
        original.repeat_type = new.repeat_type
        original.repeat_every = new.repeat_every
        original.stop_date = new.stop_date
        original.account = new.account
        original.amount = new.amount
        original.notes = new.notes
        original.reset_spawn_cache()
        if original not in self.budgets:
            self.budgets.append(original)
        self._cook(from_date=min_date)

    def delete_budgets(self, budgets):
        """Removes ``budgets`` from the document.

        :param budgets: list of :class:`.Budget`
        """
        if not budgets:
            return
        action = Action(tr('Remove Budget'))
        action.deleted_budgets |= set(budgets)
        self._undoer.record(action)
        for budget in budgets:
            self.budgets.remove(budget)
        min_date = min(b.start_date for b in budgets)
        self._cook(from_date=min_date)

    # --- Schedule
    def change_schedule(self, schedule, new_ref, repeat_type, repeat_every, stop_date):
        """Change attributes of ``schedule``.

        ``new_ref`` is a reference transaction that the schedule is going to repeat.

        :param schedule: :class:`.Schedule`
        :param new_ref: :class:`.Transaction`
        :param repeat_type: :class:`.RepeatType`
        :param stop_date: ``datetime.date``
        """
        for split in new_ref.splits:
            if split.account is not None:
                # same as in change_transaction()
                split.account = self.accounts.find(split.account.name, split.account.type)
        if schedule in self.schedules:
            action = Action(tr('Change Schedule'))
            action.change_schedule(schedule)
        else:
            action = Action(tr('Add Schedule'))
            action.added_schedules.add(schedule)
        self._undoer.record(action)
        original = schedule.ref
        min_date = min(original.date, new_ref.date)
        original.change(
            description=new_ref.description, payee=new_ref.payee,
            checkno=new_ref.checkno, notes=new_ref.notes, splits=new_ref.splits
        )
        schedule.start_date = new_ref.date
        schedule.repeat_type = repeat_type
        schedule.repeat_every = repeat_every
        schedule.stop_date = stop_date
        schedule.reset_spawn_cache()
        if schedule not in self.schedules:
            self.schedules.append(schedule)
        self._cook(from_date=min_date)

    def delete_schedules(self, schedules):
        """Removes ``schedules`` from the document.

        :param schedules: list of :class:`.Schedule`
        """
        if not schedules:
            return
        action = Action(tr('Remove Schedule'))
        action.deleted_schedules |= set(schedules)
        self._undoer.record(action)
        for schedule in schedules:
            self.schedules.remove(schedule)
        min_date = min(s.ref.date for s in schedules)
        self._cook(from_date=min_date)

    # --- Load / Save / Import
    def load_from_xml(self, filename):
        """Clears the document and loads data from ``filename``.

        ``filename`` must be a path to a moneyGuru XML document.

        :param filename: ``str``
        """
        loader = native.Loader(self.default_currency)
        try:
            loader.parse(filename)
        except FileFormatError:
            raise FileFormatError(tr('"%s" is not a moneyGuru file') % filename)
        loader.load()
        self.clear()
        self._document_id = loader.document_id
        for propname in self._properties:
            if propname in loader.properties:
                self._properties[propname] = loader.properties[propname]
        for group in loader.groups:
            self.groups.append(group)
        self.accounts = loader.accounts
        self.oven._accounts = self.accounts
        self._undoer._accounts = self.accounts
        for transaction in loader.transactions:
            self.transactions.add(transaction, True)
        for recurrence in loader.schedules:
            self.schedules.append(recurrence)
        for budget in loader.budgets:
            self.budgets.append(budget)
        self.accounts.default_currency = self.default_currency
        self._cook()
        self._undoer.set_save_point()
        self._restore_preferences_after_load()

    def save_to_xml(self, filename, autosave=False):
        """Saves the document to ``filename``.

        ``filename`` must be a path to a moneyGuru XML document.

        If ``autosave`` is true, the operation will not affect the document's
        modified state.

        :param filename: ``str``
        :param autosave: ``bool``
        """
        if self._document_id is None:
            self._document_id = uuid.uuid4().hex
        save_native(
            filename, self._document_id, self._properties, self.accounts,
            self.groups, self.transactions, self.schedules, self.budgets
        )
        if not autosave:
            self._undoer.set_save_point()
            self._dirty_flag = False

    def import_entries(self, target_account, ref_account, matches):
        """Imports entries in ``mathes`` into ``target_account``.

        ``target_account`` can be either an existing account in the document or not.

        ``ref_account`` is a reference to the temporary :class:`.Account` created by the loader.

        ``matches`` is a list of tuples ``(entry, ref)`` with ``entry`` being the entry being
        imported and ``ref`` being an existing entry in the ``target_account`` bound to ``entry``.
        ``ref`` can be ``None`` and it's only possible to have a ``ref`` side when the target
        account already exists in the document.
        """
        # Matches is a list of 2 sized tuples (entry, ref), ref being the existing entry that 'entry'
        # has been matched with. 'ref' can be None
        # PREPARATION
        # We have to look which transactions are added, which are changed. We have to see which
        # accounts will be added. Those with a name clash must be replaced (in the splits).

        added_transactions = set()
        added_accounts = set()
        to_unreconcile = set()

        def internalize(account):
            if account in self.accounts:
                return account
            if account.reference:
                found = self.accounts.find_reference(account.reference)
                if found:
                    return found
            found = self.accounts.find(account.name)
            if found:
                return found
            else:
                # we never internalize groupname
                # it doesn't hurt to change the account's groupname because
                # groups have no effect in the import window
                account.change(groupname=None)
                result = self.accounts.create_from(account)
                added_accounts.add(result)
                return result

        if target_account is None:
            target_account = internalize(ref_account)
        for entry, ref in matches:
            entry.split.account = target_account
            if ref is not None:
                to_unreconcile.add(ref.transaction)
            else:
                if entry.transaction not in self.transactions:
                    added_transactions.add(entry.transaction)
                    entry.transaction.mtime = time.time()
            for split in entry.splits:
                if split.account is None:
                    continue
                split.account = internalize(split.account)
        action = Action(tr('Import'))
        action.added_accounts |= added_accounts
        action.added_transactions |= added_transactions
        action.change_transactions(to_unreconcile, self.schedules)
        self._undoer.record(action)

        for txn in to_unreconcile:
            for split in txn.splits:
                split.reconciliation_date = None
        if ref_account.reference is not None:
            target_account.change(reference=ref_account.reference)
        for entry, ref in matches:
            for split in entry.transaction.splits:
                assert not split.account or split.account in self.accounts
            if ref is not None:
                ref.transaction.date = entry.date
                ref.split.amount = entry.split.amount
                ref.transaction.balance(ref.split, True)
                ref.split.reference = entry.split.reference
            else:
                if entry.transaction not in self.transactions:
                    self.transactions.add(entry.transaction)
        self._cook()

    def is_dirty(self):
        """Returns whether the document has been modified since the last time it was saved."""
        return self._dirty_flag or self._undoer.modified

    def set_dirty(self):
        # is_dirty() is determined by the undoer's save point, but some actions are not undoable but
        # make the document dirty (ok, it's just one action: setting doc props). That's what this
        # flag is for.
        self._dirty_flag = True

    # --- Date Range
    @property
    def date_range(self):
        """*get/set*. Current date range of the document.

        The date range is very influential of how data is displayed in the UI. For transaction and
        entry list, it tells which are shown and which are not. For reports (net worth, profit),
        it tells the scope of it (we want a net worth report for... this month? this year?
        last year?).
        """
        return self._date_range

    @date_range.setter
    def date_range(self, date_range):
        if date_range == self._date_range:
            return
        self._date_range = date_range
        self.oven.continue_cooking(date_range.end)

    # --- Undo
    def can_undo(self):
        """Returns whether the document has something to undo."""
        return self._undoer.can_undo()

    def undo_description(self):
        """Returns a string describing what would be undone if :meth:`undo` was called."""
        return self._undoer.undo_description()

    def undo(self):
        """Undo the last undoable action."""
        self._undoer.undo()
        self._cook()

    def can_redo(self):
        """Returns whether the document has something to redo."""
        return self._undoer.can_redo()

    def redo_description(self):
        """Returns a string describing what would be redone if :meth:`redo` was called."""
        return self._undoer.redo_description()

    def redo(self):
        """Redo the last redoable action."""
        self._undoer.redo()
        self._cook()

    # --- Misc
    def clear(self):
        self._document_id = None
        self.groups.clear()
        del self.schedules[:]
        del self.budgets[:]
        self._undoer.clear()
        self._dirty_flag = False
        self.excluded_accounts = set()
        self.accounts.clear()
        self.transactions.clear()
        self._cook()

    def close(self):
        self._save_preferences()

    def can_restore_from_prefs(self):
        """Returns whether the document has preferences to restore from.

        In other words, returns whether we have a document ID.
        """
        return self._document_id is not None

    def format_amount(self, amount, force_explicit_currency=False, **kwargs):
        if force_explicit_currency:
            default_currency = None
        else:
            default_currency = self.default_currency
        return format_amount(
            amount, default_currency or '', decimal_sep=self.app._decimal_sep,
            grouping_sep=self.app._grouping_sep, **kwargs
        )

    def parse_amount(self, amount, default_currency=None):
        if default_currency is None:
            default_currency = self.default_currency
        return parse_amount(amount, default_currency, auto_decimal_place=self.app._auto_decimal_place)

    def is_amount_native(self, amount):
        if amount == 0:
            return True
        return amount.currency_code == self.default_currency

    def touch(self):
        self.step += 1
        if self.app.autosave_interval and self.step % self.app.autosave_interval == 0:
            self._autosave()

    def get_default(self, key, fallback_value=None):
        if self._document_id is None:
            return fallback_value
        key = 'Doc{0}.{1}'.format(self._document_id, key)
        return self.app.get_default(key, fallback_value=fallback_value)

    def set_default(self, key, value):
        if self._document_id is None:
            return
        key = 'Doc{0}.{1}'.format(self._document_id, key)
        self.app.set_default(key, value)

    # --- Properties
    # 0=monday 6=sunday
    @property
    def first_weekday(self):
        return self._properties['first_weekday']

    @first_weekday.setter
    def first_weekday(self, value):
        if value == self._properties['first_weekday']:
            return
        self._properties['first_weekday'] = value
        self.set_dirty()

    @property
    def default_currency(self):
        return self._properties['default_currency']

    @default_currency.setter
    def default_currency(self, value):
        if value == self._properties['default_currency']:
            return
        self._properties['default_currency'] = value
        self.set_dirty()
        self.accounts.default_currency = value
        self.touch()
