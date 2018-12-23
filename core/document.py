# Copyright 2018 Virgil Dupras
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

from core.notify import Repeater
from core.util import nonone, allsame, dedupe, extract, first, flatten
from core.trans import tr

from .const import NOEDIT, DATE_FORMAT_FOR_PREFERENCES
from .exception import FileFormatError, OperationAborted
from .gui.base import GUIObject
from .loader import native
from .model._ccore import AccountList, Entry
from .model.account import Group, GroupList, AccountType
from .model.amount import parse_amount, format_amount
from .model.currency import Currencies
from .model.budget import BudgetList
from .model.date import (
    MonthRange, QuarterRange, YearRange, YearToDateRange, RunningYearRange,
    AllTransactionsRange, CustomDateRange, inc_month
)
from .model.oven import Oven
from .model.recurrence import Spawn
from .model.transaction_list import TransactionList
from .model.undo import Undoer, Action
from .saver.native import save as save_native

SELECTED_DATE_RANGE_PREFERENCE = 'SelectedDateRange'
SELECTED_DATE_RANGE_START_PREFERENCE = 'SelectedDateRangeStart'
SELECTED_DATE_RANGE_END_PREFERENCE = 'SelectedDateRangeEnd'
EXCLUDED_ACCOUNTS_PREFERENCE = 'ExcludedAccounts'

DATE_RANGE_MONTH = 'month'
DATE_RANGE_QUARTER = 'quarter'
DATE_RANGE_YEAR = 'year'
DATE_RANGE_YTD = 'ytd'
DATE_RANGE_RUNNING_YEAR = 'running_year'
DATE_RANGE_ALL_TRANSACTIONS = 'all_transactions'
DATE_RANGE_CUSTOM = 'custom'

class FilterType:
    """Available types for filter at :attr:`Document.filter_type`.

    * ``Unassigned``
    * ``Income``
    * ``Expense``
    * ``Transfer``
    * ``Reconciled``
    * ``NotReconciled``.
    """
    Unassigned = object()
    Income = object() # in etable, the filter is for increase
    Expense = object() # in etable, the filter is for decrease
    Transfer = object()
    Reconciled = object()
    NotReconciled = object()

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

class BaseDocument:
    """Provides a common base for :class:`Document` and :class:`ImportDocument`.

    Those two classes have a large subset of common behavior but still differ significantly, hence
    the class split.

    Unlike :class:`Document`, this class doesn't manage:

    * UI management (no ``view`` attribute)
    * Global scope querying
    * Date range filtering
    * Undo actions
    """
    def __init__(self, app):
        self.app = app
        self._properties = {
            'default_currency': self.app._default_currency,
        }
        #: :class:`.AccountList` containing all accounts of the document.
        self.accounts = AccountList(self.default_currency)
        #: :class:`.TransactionList` containing all transactions of the document.
        self.transactions = TransactionList()
        # `schedules` and `budgets` don't belong here, but because our oven require instances of
        # them, we tolerate this small irregularity for the sake of simplicity. However, all
        # schedules and budgets related code is up in `Document`.
        #
        # I did not manage to create a repeatable test for it, but self.schedules has to be
        # an ordered collection because the order in which the spawns are created must stay the
        # same
        self.schedules = []
        self.budgets = BudgetList()
        self.oven = Oven(self.accounts, self.transactions, self.schedules, self.budgets)

    # --- Private
    def _add_transactions(self, transactions):
        if not transactions:
            return
        for txn in transactions:
            self.transactions.add(txn)
        min_date = min(t.date for t in transactions)
        self._cook(from_date=min_date)

    def _change_transaction(self, transaction, global_scope=False, **kwargs):
        date = kwargs.get('date', NOEDIT)
        date_changed = date is not NOEDIT and date != transaction.date
        kws = {k: v for k, v in kwargs.items() if v is not NOEDIT}
        transaction.change(**kws)
        # XXX This Spawn-related code piece doesn't belong in `BaseDocument`, but in the middle of
        # a big refactoring, there wasn't an easy way to extract it out to `Document` without
        # needlessly complexifying the code. Some day, we'll have to find an elegant solution to
        # this. In fact, it's the same thing with all these `global_scope` flags we have to
        # propagate everywhere. No easy solution right now.
        if isinstance(transaction, Spawn):
            if global_scope:
                transaction.recurrence.change_globally(transaction)
            else:
                transaction.recurrence.delete(transaction)
                materialized = transaction.replicate()
                self.transactions.add(materialized)
        else:
            if transaction not in self.transactions:
                self.transactions.add(transaction)
            elif date_changed:
                self.transactions.move_last(transaction)
        self.transactions.clear_cache()

    def _clear(self):
        self.accounts.clear()
        self.transactions.clear()
        self._cook()

    def _cook(self, from_date=None):
        # Without date ranges and spawns, it's OK to pass `None` as an `until_date`.
        self.oven.cook(from_date=from_date, until_date=None)

    # --- Public
    def change_transaction(self, original, new, global_scope=False):
        """Changes the attributes of ``original`` so that they match those of ``new``.

        This is used by the :class:`.TransactionPanel`, and ``new`` is originally a copy of
        ``original`` which has been changed. Accounts linked to splits in ``new`` don't have to be
        accounts that are part of the document. This method will automatically internalize accounts
        linked to splits (and create new accounts if necessary).

        If ``new``'s date is outside of the current date range, the date range will automatically be
        changed so that it contains ``new``.

        If ``original`` is a schedule :class:`.Spawn`, the UI will be queried for a scope, which
        might result in the change being aborted.

        After the transaction change, ``transaction_changed`` is broadcasted.

        :param original: :class:`.Transaction`
        :param new: :class:`.Transaction`, a modified copy of ``original``.
        :param bool global_scope: Whether this changes affect the whole recurrence (if applicable)
        """
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

    def change_transactions(
            self, transactions, date=NOEDIT, description=NOEDIT, payee=NOEDIT, checkno=NOEDIT,
            from_=NOEDIT, to=NOEDIT, amount=NOEDIT, currency=NOEDIT, global_scope=False):
        """Properly sets properties for ``transactions``.

        Changes the attributes of every transaction in ``transactions`` to the values specified in
        the arguments (arguments left to ``NOEDIT`` have no effect).

        ``from_`` and ``to`` are account **names** rather than being :class:`.Account` instances. If
        the names don't exist, they'll automatically be created.

        If any transaction in ``transactions`` is a schedule :class:`.Spawn`, the UI will be queried
        for a scope, which might result in the change being aborted.

        After the transaction change, ``transaction_changed`` is broadcasted.

        :param date: ``datetime.date``
        :param description: ``str``
        :param payee: ``str``
        :param checkno: ``str``
        :param from_: ``str`` (account name)
        :param to: ``str`` (account name)
        :param amount: :class:`.Amount`
        :param currency: :class:`.Currency`
        :param bool global_scope: Whether this changes affect the whole recurrence (if applicable)
        """
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

    def delete_transactions(self, transactions, from_account=None, global_scope=False):
        """Removes every transaction in ``transactions`` from the document.

        If any transaction in ``transactions`` is a schedule :class:`.Spawn`, the UI will be queried
        for a scope, which might result in the deletion being aborted.

        After the transaction deletion, ``transaction_deleted`` is broadcasted.

        ``from_account`` represents, in the UI, the account from which this deletion was triggered.
        By specifying it, you will prevent it from being automatically purged by
        `clean_empty_categories` (we don't want to delete an account that is actively being
        worked on by the user).

        :param transactions: a collection of :class:`.Transaction`.
        :param from_account: the :class:`.Account` from which the operation takes place, if any.
        :param bool global_scope: Whether this changes affect the whole recurrence (if applicable)
        """
        for txn in transactions:
            if isinstance(txn, Spawn):
                if global_scope:
                    txn.recurrence.stop_before(txn)
                else:
                    txn.recurrence.delete(txn)
            else:
                self.transactions.remove(txn)
        min_date = min(t.date for t in transactions)
        self._cook(from_date=min_date)
        self.accounts.clean_empty_categories(from_account)

    def duplicate_transactions(self, transactions):
        """Create copies of ``transactions`` in the document.

        For each transaction in ``transactions``, add a new transaction with the same attributes to
        the document.

        After the operation, ``transaction_changed`` is broadcasted.

        :param transactions: a collection of :class:`.Transaction` to duplicate.
        """
        duplicated = [txn.replicate() for txn in transactions]
        self._add_transactions(duplicated)

    def move_transactions(self, transactions, to_transaction):
        """Re-orders ``transactions`` so that they are right before ``to_transaction``.

        If ``to_transaction`` is ``None``, it means that we move transactions at the end of the
        list.

        Make sure your move is legal by calling :meth:`can_move_transactions` first.

        After the move, ``transaction_changed`` is broadcasted.

        :param transactions: a collection of :class:`.Transaction` to move.
        :param to_transaction: target :class:`.Transaction` to move to.
        """
        for transaction in transactions:
            self.transactions.move_before(transaction, to_transaction)
        self._cook()

    def change_entry(
            self, entry, date=NOEDIT, reconciliation_date=NOEDIT, description=NOEDIT, payee=NOEDIT,
            checkno=NOEDIT, transfer=NOEDIT, amount=NOEDIT, global_scope=False):
        """Properly sets properties for ``entry``.

        Changes the attributes of ``entry`` (and the transaction in which ``entry`` is) to specified
        values and then post a ``transaction_changed`` notification. Attributes with ``NOEDIT``
        values are not touched.

        ``transfer`` is the name of the transfer to assign the entry to. If it's not found, a new
        account will be created.

        :param entry: :class:`.Entry`
        :param date: ``datetime.date``
        :param reconciliation_date: ``datetime.date``
        :param description: ``str``
        :param payee: ``str``
        :param checkno: ``str``
        :param transfer: ``str`` (name of account)
        :param amount: :class:`.Amount`
        :param bool global_scope: Whether this changes affect the whole recurrence (if applicable)
        """
        assert entry is not None
        if date is not NOEDIT and amount is not NOEDIT and amount != 0:
            Currencies.get_rates_db().ensure_rates(date, [amount.currency_code, entry.account.currency])
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

    def delete_entries(self, entries):
        """Remove transactions in which ``entries`` belong from the document's transaction list.

        :param entries: list of :class:`.Entry`
        """
        from_account = first(entries).account
        transactions = dedupe(e.transaction for e in entries)
        self.delete_transactions(transactions, from_account=from_account)

    def clear(self):
        """Removes all data from the document (transactions, accounts, schedules, etc.)."""
        self._clear()

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

    # --- Properties
    @property
    def default_currency(self):
        return self._properties['default_currency']


class Document(BaseDocument, Repeater, GUIObject):
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

    Subclasses :class:`BaseDocument`, :class:`core.notify.Repeater` and
    :class:`hscommon.gui.base.GUIObject`.
    """
    REPEATED_NOTIFICATIONS = {'saved_custom_ranges_changed'}

    def __init__(self, app):
        BaseDocument.__init__(self, app)
        Repeater.__init__(self, app)
        GUIObject.__init__(self)
        self._properties.update({
            'first_weekday': 0,
            'ahead_months': 3,
            'year_start_month': 1,
        })
        #: Set of accounts that are currently in "excluded" state.
        self.excluded_accounts = set()
        #: :class:`.GroupList` containing all account groups of the document.
        self.groups = GroupList()
        self._undoer = Undoer(self.accounts, self.groups, self.transactions, self.schedules, self.budgets)
        self._date_range = YearRange(datetime.date.today())
        self._filter_string = ''
        self._filter_type = None
        self._document_id = None
        self._dirty_flag = False
        self._restore_preferences()

    # --- Private
    def _adjust_date_range(self, new_date):
        new_date_range = self.date_range.adjusted(new_date)
        if new_date_range is None:
            return False
        # We have to manually set the date range and send notifications because ENTRY_CHANGED
        # must happen between DATE_RANGE_WILL_CHANGE and DATE_RANGE_CHANGED
        # Note that there are no tests for this, as the current doesn't really allow to test
        # for the order of the gui calls (and this exception doesn't mean that we should).
        self.notify('date_range_will_change')
        self._date_range = new_date_range
        self.oven.continue_cooking(new_date_range.end)
        self.notify('transaction_changed')
        self.notify('date_range_changed')
        return True

    def _async_autosave(self):
        # Because this method is called asynchronously, it's possible that, if unlucky, it happens
        # exactly as the user is commiting a change. In these cases, the autosaved file might be a
        # save of the data in a quite weird state. I think this risk is acceptable. The alternative
        # is to put locks everywhere, which would complexify the application.
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

    def _clear(self):
        self._document_id = None
        self.groups.clear()
        del self.schedules[:]
        del self.budgets[:]
        self._undoer.clear()
        self._dirty_flag = False
        BaseDocument._clear(self)

    def _cook(self, from_date=None):
        self.oven.cook(from_date=from_date, until_date=self.date_range.end)

    def _get_action_from_changed_transactions(self, transactions, global_scope=False):
        if len(transactions) == 1 and not isinstance(transactions[0], Spawn) \
                and transactions[0] not in self.transactions:
            action = Action(tr('Add transaction'))
            action.added_transactions.add(transactions[0])
        else:
            action = Action(tr('Change transaction'))
            action.change_transactions(transactions)
        if global_scope:
            spawns, txns = extract(lambda x: isinstance(x, Spawn), transactions)
            for schedule in {spawn.recurrence for spawn in spawns}:
                action.change_schedule(schedule)
        return action

    def _query_for_scope_if_needed(self, transactions):
        """Queries the UI for change scope if there's any Spawn among transactions.

        Returns whether the chosen scope is global
        Raises OperationAborted if the user cancels the operation.
        """
        if any(isinstance(txn, Spawn) for txn in transactions):
            scope = self.view.query_for_schedule_scope()
            if scope == ScheduleScope.Cancel:
                raise OperationAborted()
            return scope == ScheduleScope.Global
        else:
            return False

    def _reconcile_spawn_split(self, entry, reconciliation_date):
        # returns a reference to the corresponding materialized split
        entry.transaction.recurrence.delete(entry.transaction)
        materialized = entry.transaction.replicate()
        self.transactions.add(materialized)
        split_index = entry.transaction.splits.index(entry.split)
        materialized_split = materialized.splits[split_index]
        materialized_split.reconciliation_date = reconciliation_date
        return materialized, materialized_split

    def _refresh_date_range(self):
        """Refreshes the date range to make sure that it's in accordance with the current date
        range related preference (year start and ahead months). Call this when these prefs changed.
        """
        if isinstance(self.date_range, RunningYearRange):
            self.select_running_year_range()
        elif isinstance(self.date_range, AllTransactionsRange):
            self.select_all_transactions_range()
        elif isinstance(self.date_range, YearRange):
            if datetime.date.today() in self.date_range:
                starting_point = datetime.date.today()
            else:
                starting_point = self.date_range
            self.select_year_range(starting_point=starting_point)
        elif isinstance(self.date_range, YearToDateRange):
            self.select_year_to_date_range()

    def _restore_preferences(self):
        start_date = self.app.get_default(SELECTED_DATE_RANGE_START_PREFERENCE)
        if start_date:
            start_date = datetime.datetime.strptime(start_date, DATE_FORMAT_FOR_PREFERENCES).date()
        end_date = self.app.get_default(SELECTED_DATE_RANGE_END_PREFERENCE)
        if end_date:
            end_date = datetime.datetime.strptime(end_date, DATE_FORMAT_FOR_PREFERENCES).date()
        selected_range = self.app.get_default(SELECTED_DATE_RANGE_PREFERENCE)
        if selected_range == DATE_RANGE_MONTH:
            self.select_month_range(start_date)
        elif selected_range == DATE_RANGE_QUARTER:
            self.select_quarter_range(start_date)
        elif selected_range == DATE_RANGE_YEAR:
            self.select_year_range(start_date)
        elif selected_range == DATE_RANGE_YTD:
            self.select_year_to_date_range()
        elif selected_range == DATE_RANGE_RUNNING_YEAR:
            self.select_running_year_range()
        elif selected_range == DATE_RANGE_CUSTOM and start_date and end_date:
            self.select_custom_date_range(start_date, end_date)

    def _restore_preferences_after_load(self):
        # some preference need the file loaded before attempting a restore
        logging.debug('restore_preferences_after_load() beginning')
        excluded_account_names = set(nonone(self.get_default(EXCLUDED_ACCOUNTS_PREFERENCE), []))
        self.excluded_accounts = {a for a in self.accounts if a.name in excluded_account_names}
        selected_range = self.app.get_default(SELECTED_DATE_RANGE_PREFERENCE)
        if selected_range == DATE_RANGE_ALL_TRANSACTIONS: # only works after load
            self.select_all_transactions_range()
        self.notify('document_restoring_preferences')

    def _save_preferences(self):
        dr = self.date_range
        selected_range = DATE_RANGE_MONTH
        if isinstance(dr, QuarterRange):
            selected_range = DATE_RANGE_QUARTER
        elif isinstance(dr, YearRange):
            selected_range = DATE_RANGE_YEAR
        elif isinstance(dr, YearToDateRange):
            selected_range = DATE_RANGE_YTD
        elif isinstance(dr, RunningYearRange):
            selected_range = DATE_RANGE_RUNNING_YEAR
        elif isinstance(dr, AllTransactionsRange):
            selected_range = DATE_RANGE_ALL_TRANSACTIONS
        elif isinstance(dr, CustomDateRange):
            selected_range = DATE_RANGE_CUSTOM
        self.app.set_default(SELECTED_DATE_RANGE_PREFERENCE, selected_range)
        str_start_date = dr.start.strftime(DATE_FORMAT_FOR_PREFERENCES)
        self.app.set_default(SELECTED_DATE_RANGE_START_PREFERENCE, str_start_date)
        str_end_date = dr.end.strftime(DATE_FORMAT_FOR_PREFERENCES)
        self.app.set_default(SELECTED_DATE_RANGE_END_PREFERENCE, str_end_date)
        excluded_account_names = [a.name for a in self.excluded_accounts]
        self.set_default(EXCLUDED_ACCOUNTS_PREFERENCE, excluded_account_names)

    # --- Account
    def change_accounts(
            self, accounts, name=NOEDIT, type=NOEDIT, currency=NOEDIT, group=NOEDIT,
            account_number=NOEDIT, inactive=NOEDIT, notes=NOEDIT):
        """Properly sets properties for ``accounts``.

        Sets ``accounts``' properties in a proper manner and post a ``account_changed``
        notification. Attributes corresponding to arguments set to ``NOEDIT`` will not be touched.

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
        action = Action(tr('Change account'))
        action.change_accounts(accounts)
        for account in accounts:
            if name is not NOEDIT and name:
                other = self.accounts.find(name)
                if (other is not None) and (other != account):
                    return False
                self.accounts.rename_account(account, name.strip())
            if (type is not NOEDIT) and (type != account.type):
                account.type = type
                account.groupname = None
            if currency is not NOEDIT:
                entries = self.accounts.entries_for_account(account)
                assert not any(e.reconciled for e in entries)
                account.currency = currency
            if group is not NOEDIT:
                account.groupname = group.name if group else None
            if account_number is not NOEDIT:
                account.account_number = account_number
            if inactive is not NOEDIT:
                account.inactive = inactive
            if notes is not NOEDIT:
                account.notes = notes
        self._undoer.record(action)
        self._cook()
        self.transactions.clear_cache()
        self.notify('account_changed')
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
            transactions = {e.transaction for e in all_entries if not isinstance(e.transaction, Spawn)}
            transactions = {t for t in transactions if not t.affected_accounts() - accounts}
            action.deleted_transactions |= transactions
        action.change_entries(all_entries)
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
        self.notify('account_deleted')

    def new_account(self, type, group):
        """Create a new account in the document.

        Creates a new account of type ``type``, within the ``group`` (which can be ``None`` to
        indicate no group). The new account will have a unique name based on the string
        "New Account" (if it exists already, a unique number will be appended to it). Once created,
        the account is added to the account list, and ``account_added`` is broadcasted.

        :param type: :class:`.AccountType`
        :param group: :class:`.Group`
        :rtype: :class:`.Account`
        """
        name = self.accounts.new_name(tr('New account'))
        account = self.accounts.create(name, self.default_currency, type)
        account.groupname = group.name if group else None
        action = Action(tr('Add account'))
        action.added_accounts.add(account)
        self._undoer.record(action)
        self.notify('account_added')
        return account

    def toggle_accounts_exclusion(self, accounts):
        """Toggles "excluded" state for ``accounts``.

        If the current excluded state for ``accounts`` is not homogenous, we set all non-excluded
        accounts as excluded and leave excluded accounts in their current state. Afterwards,
        ``accounts_excluded`` is broadcasted.

        :param accounts: a ``set`` of :class:`.Account`
        """
        if accounts <= self.excluded_accounts: # all accounts are already excluded. re-include all
            self.excluded_accounts -= accounts
        else:
            self.excluded_accounts |= accounts
        self.notify('accounts_excluded')

    # --- Group
    def change_group(self, group, name=NOEDIT):
        """Properly sets properties for ``group``.

        Sets ``group``'s properties in a proper manner and post a ``account_changed`` notification.
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
        self.notify('account_changed')
        return True

    def delete_groups(self, groups):
        """Removes ``groups`` from the document.

        Removes ``groups`` from the group list and broadcasts ``account_deleted``. All accounts
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
            account.groupname = None
        self.notify('account_deleted')

    def new_group(self, type):
        """Creates a new group of type ``type``.

        The new group will have a unique name based on the string "New Group" (if it exists, a
        unique number will be appended to it). Once created, the group is added to the group list,
        and ``account_added`` is broadcasted.

        :param type: :class:`.AccountType`
        :rtype: :class:`.Group`
        """
        name = self.groups.new_name(tr('New group'), type)
        group = Group(name, type)
        action = Action(tr('Add group'))
        action.added_groups.add(group)
        self._undoer.record(action)
        self.groups.append(group)
        self.notify('account_added')
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
        if any(isinstance(txn, Spawn) for txn in transactions):
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

        Overrides :meth:`BaseDocument.change_transaction`.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param original: :class:`.Transaction`
        :param new: :class:`.Transaction`, a modified copy of ``original``.
        """
        global_scope = self._query_for_scope_if_needed([original])
        action = Action(tr('Change transaction'))
        action.change_transactions([original])
        self._undoer.record(action)
        BaseDocument.change_transaction(self, original, new, global_scope=global_scope)
        if not self._adjust_date_range(original.date):
            self.notify('transaction_changed')

    @handle_abort
    def change_transactions(
            self, transactions, date=NOEDIT, description=NOEDIT, payee=NOEDIT, checkno=NOEDIT,
            from_=NOEDIT, to=NOEDIT, amount=NOEDIT, currency=NOEDIT):
        """Properly sets properties for ``transactions``.

        Overrides :meth:`BaseDocument.change_transactions`.

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
        BaseDocument.change_transactions(
            self, transactions, date=date, description=description, payee=payee, checkno=checkno,
            from_=from_, to=to, amount=amount, currency=currency, global_scope=global_scope
        )
        if not self._adjust_date_range(transactions[-1].date):
            self.notify('transaction_changed')
        if action.changed_schedules:
            self.notify('schedule_changed')

    @handle_abort
    def delete_transactions(self, transactions, from_account=None):
        """Removes every transaction in ``transactions`` from the document.

        Overrides :meth:`BaseDocument.delete_transactions`.

        Adds undo recording, global scope querying, date range adjustments and UI triggers.

        :param transactions: a collection of :class:`.Transaction`.
        :param from_account: the :class:`.Account` from which the operation takes place, if any.
        """
        action = Action(tr('Remove transaction'))
        spawns, txns = extract(lambda x: isinstance(x, Spawn), transactions)
        global_scope = self._query_for_scope_if_needed(spawns)
        schedules = set(spawn.recurrence for spawn in spawns)
        action.deleted_transactions |= set(txns)
        for schedule in schedules:
            action.change_schedule(schedule)
        self._undoer.record(action)
        BaseDocument.delete_transactions(
            self, transactions, from_account=from_account, global_scope=global_scope
        )
        self.notify('transaction_deleted')
        if action.changed_schedules:
            self.notify('schedule_changed')

    def duplicate_transactions(self, transactions):
        """Create copies of ``transactions`` in the document.

        Overrides :meth:`BaseDocument.duplicate_transactions`.

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
        self.notify('transaction_changed')

    def move_transactions(self, transactions, to_transaction):
        """Re-orders ``transactions`` so that they are right before ``to_transaction``.

        Overrides :meth:`BaseDocument.move_transactions`.

        Adds undo recording and UI triggers.

        :param transactions: a collection of :class:`.Transaction` to move.
        :param to_transaction: target :class:`.Transaction` to move to.
        """
        affected = set(transactions)
        affected_date = transactions[0].date
        affected |= set(self.transactions.transactions_at_date(affected_date))
        action = Action(tr('Move transaction'))
        action.change_transactions(affected)
        self._undoer.record(action)
        BaseDocument.move_transactions(self, transactions, to_transaction)
        self.notify('transaction_changed')

    # --- Entry
    @handle_abort
    def change_entry(
            self, entry, date=NOEDIT, reconciliation_date=NOEDIT, description=NOEDIT, payee=NOEDIT,
            checkno=NOEDIT, transfer=NOEDIT, amount=NOEDIT):
        """Properly sets properties for ``entry``.

        Overrides :meth:`BaseDocument.change_entry`.

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
        if reconciliation_date is NOEDIT:
            global_scope = self._query_for_scope_if_needed([entry.transaction])
        else:
            global_scope = False # It doesn't make sense to set a reconciliation date globally
        action = self._get_action_from_changed_transactions([entry.transaction], global_scope)
        self._undoer.record(action)
        if reconciliation_date is not NOEDIT and isinstance(entry.transaction, Spawn):
            newtxn, newsplit = self._reconcile_spawn_split(entry, reconciliation_date)
            entry = Entry(newsplit, newtxn)
            action.added_transactions.add(newtxn)
        BaseDocument.change_entry(
            self, entry, date=date, reconciliation_date=reconciliation_date,
            description=description, payee=payee, checkno=checkno, transfer=transfer,
            amount=amount, global_scope=global_scope
        )
        if not self._adjust_date_range(entry.date):
            self.notify('transaction_changed')

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
        action.change_entries(entries)
        min_date = min(entry.date for entry in entries)
        spawns, entries = extract(lambda e: isinstance(e.transaction, Spawn), entries)
        for spawn in spawns:
            action.change_schedule(spawn.transaction.recurrence)
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
        self.notify('transaction_changed')

    # --- Budget
    def budgeted_amount_for_target(self, target, date_range, filter_excluded=True):
        """Returns the amount budgeted for **all** budgets targeting ``target``.

        The amount is pro-rated according to ``date_range``.

        The currency of the result is ``target``'s currency. The result is normalized (reverted if
        target is a liability).

        If target is ``None``, all accounts are used.

        If ``filter_excluded`` is true, we ignore accounts in "excluded" state.

        :param target: :class:`.Account`
        :param date_range: ``datetime.date``
        :param filter_excluded: ``bool``
        :rtype: :class:`.Amount`
        """
        if target is None:
            budgets = self.budgets[:]
            currency = self.default_currency
        else:
            budgets = self.budgets.budgets_for_target(target)
            currency = target.currency
        if filter_excluded:
            # we must remove any budget touching an excluded account.
            is_not_excluded = lambda b: (b.account not in self.excluded_accounts)\
                and (b.target not in self.excluded_accounts)
            budgets = list(filter(is_not_excluded, budgets))
        if not budgets:
            return 0
        budgeted_amount = sum(-b.amount_for_date_range(date_range, currency=currency) for b in budgets)
        if target is not None:
            budgeted_amount = target.normalize_amount(budgeted_amount)
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
        original.target = new.target
        original.amount = new.amount
        original.notes = new.notes
        original.reset_spawn_cache()
        if original not in self.budgets:
            self.budgets.append(original)
        self._cook(from_date=min_date)
        self.notify('budget_changed')

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
        self.notify('budget_deleted')

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
        self.notify('schedule_changed')

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
        self.notify('schedule_deleted')

    # --- Load / Save / Import
    def adjust_example_file(self):
        """Adjusts all document's transactions so that they become current.

        This is used when loading the example document so that it's not necessary to do it manually.
        """
        def inc_month_overflow(refdate, count):
            newdate = inc_month(refdate, count)
            if newdate.day < refdate.day: # must overflow
                newdate += datetime.timedelta(days=refdate.day-newdate.day)
            return newdate

        latest_date = self.transactions.last().date
        TODAY = datetime.date.today()
        year_diff = TODAY.year - latest_date.year
        month_diff = year_diff * 12 + (TODAY.month - latest_date.month)
        if month_diff < 1:
            return
        for txn in list(self.transactions):
            txn.date = inc_month_overflow(txn.date, month_diff)
            if txn.date > TODAY:
                self.transactions.remove(txn)
            for split in txn.splits:
                if split.reconciliation_date is not None:
                    split.reconciliation_date = txn.date
        for schedule in self.schedules:
            date2exception = schedule.date2exception
            schedule.start_date = inc_month_overflow(schedule.start_date, month_diff)
            if schedule.stop_date is not None:
                schedule.stop_date = inc_month_overflow(schedule.stop_date, month_diff)
            # we delete any spawn that is not in the future
            for spawn in schedule.get_spawns(end=TODAY):
                schedule.delete(spawn)
            # This will not work for weekly schedules, but the only reason we have this here is
            # for then the student loan stops in the example document (last payment is different)
            for date, exception in list(date2exception.items()):
                if exception is None:
                    continue
                newdate = inc_month_overflow(date, month_diff)
                schedule.date2exception[newdate] = exception
        self._cook()
        self.notify('document_changed') # do it again to refresh the guis

    def clear(self):
        """Removes all data from the document (transactions, accounts, schedules, etc.)."""
        self._clear()
        self.notify('document_changed')

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
        self._clear()
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
            self.transactions.add(transaction, position=transaction.position)
        for recurrence in loader.schedules:
            self.schedules.append(recurrence)
        for budget in loader.budgets:
            self.budgets.append(budget)
        self.accounts.default_currency = self.default_currency
        self._cook()
        self._restore_preferences_after_load()
        self.notify('document_changed')
        self._undoer.set_save_point()
        self._refresh_date_range()

    def save_to_xml(self, filename, autosave=False):
        """Saves the document to ``filename``.

        ``filename`` must be a path to a moneyGuru XML document.

        If ``autosave`` is true, the operation will not affect the document's modified state and
        will not make editing stop, if editing there is (like it normally does without the autosave
        flag to make sure that the input being currently done by the user is saved).

        :param filename: ``str``
        :param autosave: ``bool``
        """
        # When called from _async_autosave, it should not disrupt the user: no stop edition, no
        # change in the save state.
        if not autosave:
            self.stop_edition()
        if self._document_id is None:
            self._document_id = uuid.uuid4().hex
        save_native(
            filename, self._document_id, self._properties, self.accounts, self.groups,
            self.transactions, self.schedules, self.budgets
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
            if account.reference:
                found = self.accounts.find_reference(account.reference)
                if found:
                    return found
            found = self.accounts.find(account.name)
            if found:
                return found
            else:
                result = self.accounts.create_from(account)
                added_accounts.add(result)
                return result

        if target_account == ref_account and target_account not in self.accounts:
            target_account = internalize(target_account)
        for entry, ref in matches:
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
            if target_account != ref_account:
                entry.split.account = target_account
        action = Action(tr('Import'))
        action.added_accounts |= added_accounts
        action.added_transactions |= added_transactions
        action.change_transactions(to_unreconcile)
        self._undoer.record(action)

        for txn in to_unreconcile:
            for split in txn.splits:
                split.reconciliation_date = None
        if target_account != ref_account and ref_account.reference is not None:
            target_account.reference = ref_account.reference
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
        self.notify('transactions_imported')

    def is_dirty(self):
        """Returns whether the document has been modified since the last time it was saved."""
        return self._dirty_flag or self._undoer.modified

    def set_dirty(self):
        # is_dirty() is determined by the undoer's save point, but some actions are not undoable but
        # make the document dirty (ok, it's just one action: setting doc props). That's what this
        # flag is for.
        self._dirty_flag = True

    # --- Date Range
    def select_month_range(self, starting_point):
        """Sets :attr:`date_range` to a :class:`.MonthRange`.

        :param starting_point: ``datetime.date`` around which to wrap the range.
        """
        self.date_range = MonthRange(starting_point)

    def select_quarter_range(self, starting_point):
        """Sets :attr:`date_range` to a :class:`.QuarterRange`.

        :param starting_point: ``datetime.date`` around which to wrap the range.
        """
        self.date_range = QuarterRange(starting_point)

    def select_year_range(self, starting_point):
        """Sets :attr:`date_range` to a :class:`.YearRange`.

        :param starting_point: ``datetime.date`` around which to wrap the range.
        """
        self.date_range = YearRange(starting_point, year_start_month=self.year_start_month)

    def select_year_to_date_range(self):
        """Sets :attr:`date_range` to a :class:`.YearToDateRange`."""
        self.date_range = YearToDateRange(year_start_month=self.year_start_month)

    def select_running_year_range(self):
        """Sets :attr:`date_range` to a :class:`.RunningYearRange`."""
        self.date_range = RunningYearRange(ahead_months=self.ahead_months)

    def select_all_transactions_range(self):
        """Sets :attr:`date_range` to a :class:`.AllTransactionsRange`."""
        if not self.transactions:
            return
        first_date = self.transactions.first().date
        last_date = self.transactions.last().date
        self.date_range = AllTransactionsRange(
            first_date=first_date, last_date=last_date,
            ahead_months=self.ahead_months
        )

    def select_custom_date_range(self, start_date=None, end_date=None):
        """Sets :attr:`date_range` to a :class:`.CustomDateRange`.

        :param start_date: ``datetime.date``
        :param end_date: ``datetime.date``
        """
        if start_date is not None and end_date is not None:
            self.date_range = CustomDateRange(start_date, end_date, self.app.format_date)
        else: # summon the panel
            self.notify('custom_date_range_selected')

    def select_prev_date_range(self):
        """If the current date range is navigable, select the previous range."""
        if self.date_range.can_navigate:
            self.date_range = self.date_range.prev()

    def select_next_date_range(self):
        """If the current date range is navigable, select the next range."""
        if self.date_range.can_navigate:
            self.date_range = self.date_range.next()

    def select_today_date_range(self):
        """If the current date range is navigable, select the range containing today."""
        if self.date_range.can_navigate:
            self.date_range = self.date_range.around(datetime.date.today())

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
        self.stop_edition()
        self.notify('date_range_will_change')
        self._date_range = date_range
        self.oven.continue_cooking(date_range.end)
        self.notify('date_range_changed')

    # --- Undo
    def can_undo(self):
        """Returns whether the document has something to undo."""
        return self._undoer.can_undo()

    def undo_description(self):
        """Returns a string describing what would be undone if :meth:`undo` was called."""
        return self._undoer.undo_description()

    def undo(self):
        """Undo the last undoable action."""
        self.stop_edition()
        self._undoer.undo()
        self._cook()
        self.notify('performed_undo_or_redo')

    def can_redo(self):
        """Returns whether the document has something to redo."""
        return self._undoer.can_redo()

    def redo_description(self):
        """Returns a string describing what would be redone if :meth:`redo` was called."""
        return self._undoer.redo_description()

    def redo(self):
        """Redo the last redoable action."""
        self.stop_edition()
        self._undoer.redo()
        self._cook()
        self.notify('performed_undo_or_redo')

    # --- Misc
    def close(self):
        """Cleanup the document and close it.

        Saves preferences and tells GUI elements about the document closing (so that they can save
        their own preferences if needed).
        """
        self._save_preferences()
        self.notify('document_will_close')

    def stop_edition(self):
        """Call this when some operation (such as a panel loading) requires the other GUIs to save
        their edits and stop edition.
        """
        self.notify('edition_must_stop')

    def can_restore_from_prefs(self):
        """Returns whether the document has preferences to restore from.

        In other words, returns whether we have a document ID.
        """
        return self._document_id is not None

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
    @property
    def filter_string(self):
        """*get/set*. Restrict visible elements in lists to those matching the string.

        When set to an non empty string, it restricts visible transactions/entries in
        :class:`.TransactionTable` and :class:`.EntryTable` to those matching with the string.
        """
        return self._filter_string

    @filter_string.setter
    def filter_string(self, value):
        value = nonone(value, '').strip()
        if value == self._filter_string:
            return
        self._filter_string = value
        self.notify('filter_applied')

    # use FilterType.* consts or None
    @property
    def filter_type(self):
        """*get/set*. Restrict visible elements in lists to those matching the type.

        When set to something else than ``None``, it restricts visible transactions/entries in
        :class:`.TransactionTable` and :class:`.EntryTable` to those matching having the specified
        :class:`.FilterType`
        """
        return self._filter_type

    @filter_type.setter
    def filter_type(self, value):
        if value is self._filter_type:
            return
        self.stop_edition()
        self._filter_type = value
        self.notify('filter_applied')

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
        self.notify('first_weekday_changed')

    @property
    def ahead_months(self):
        return self._properties['ahead_months']

    @ahead_months.setter
    def ahead_months(self, value):
        assert 0 <= value <= 11
        if value == self._properties['ahead_months']:
            return
        self._properties['ahead_months'] = value
        self.set_dirty()
        self._refresh_date_range()

    @property
    def year_start_month(self):
        return self._properties['year_start_month']

    @year_start_month.setter
    def year_start_month(self, value):
        assert 1 <= value <= 12
        if value == self._properties['year_start_month']:
            return
        self._properties['year_start_month'] = value
        self.set_dirty()
        self._refresh_date_range()

    @BaseDocument.default_currency.setter
    def default_currency(self, value):
        if value == self._properties['default_currency']:
            return
        self._properties['default_currency'] = value
        self.set_dirty()
        self.accounts.default_currency = value
        self.notify('document_changed')

    # --- Events
    def must_autosave(self):
        # this is called async
        self._async_autosave()

class ImportDocument(BaseDocument):
    """A document used to as a segregation area to operate on core model data before importing.

    Inherits all capabilities of the ``BaseDocument`` superclass with some small modifications
    pertinent to the importing of data.

    Subclasses :class:`core.document.BaseDocument`.
    """

    def __init__(self, app):
        self.parsing_date_format = None
        self.exported_accounts = dict()
        self.cached_transactions = dict()
        self.cook_flag = False
        BaseDocument.__init__(self, app)

    def reset_from_loader(self, loader, parsing_date_format):
        self.clear()
        self.parsing_date_format = parsing_date_format
        self.accounts = loader.accounts
        # we don't import groups, and we don't want them to mess our document
        for account in self.accounts:
            account.groupname = None
        self.transactions = loader.transactions
        self.schedules = loader.schedules
        self.budgets = loader.budgets
        self.oven = loader.oven

    @property
    def ahead_months(self):
        return 0

    def _get_dateformat(self):

        # We sometimes want to utilize the parsing date format
        # vs the application date format, so this method was added
        # to override that default behavior in document.
        if self.parsing_date_format is None:
            return BaseDocument._get_dateformat(self)
        else:
            return self.parsing_date_format

    def cook(self):
        """Refresh account entries for the purpose of importing.
        Unlike the main document, the import document sometimes has specific actions
        it performs.  We don't want to cook after every action, but at select points
        in the import cycle. This requires the import window to be able to tell it
        to re-do it's account entries.
        """
        self.cook_flag = True
        self.oven.cook(from_date=None, until_date=None)

    def _cook(self, from_date=None):
        pass

