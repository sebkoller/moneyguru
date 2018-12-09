# Copyright 2016 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from functools import partial

from .entry import EntryList
from .sort import sort_string
from ..exception import DuplicateAccountNameError
from ..const import Const

class AccountType:
    """Enum of all possible account types.

    * ``Asset``
    * ``Liability``
    * ``Income``
    * ``Expense``

    Special values:

    * ``All``: set containing all account types
    * ``InOrder``: all account type in "sort" order.
    """
    Asset = 'asset'
    Liability = 'liability'
    Income = 'income'
    Expense = 'expense'
    InOrder = [Asset, Liability, Income, Expense]
    All = set(InOrder)

# Placeholder when an argument is not given
NOT_GIVEN = Const("NOT_GIVEN")
ACCOUNT_SORT_KEY = lambda a: (AccountType.InOrder.index(a.type), sort_string(a.name))

def sort_accounts(accounts):
    """Sort accounts according first to their type, then to their name.
    """
    accounts.sort(key=ACCOUNT_SORT_KEY)

class Account:
    """Represents an account (in the "accounting" sense).

    Accounts in moneyGuru don't hold much information (:class:`.Transaction` holds the bulk of a
    document's juicy information). It's there as a unique identifier to assign :class:`.Split` to.

    Initialization argument simply set initial values for their relevant attributes, :attr:`name`,
    :attr:`currency` and :attr:`type`.
    """
    COUNTER = 1

    def __init__(self, name, currency, type):
        self.id = Account.COUNTER
        Account.COUNTER += 1
        #: Name of the account. Must be unique in the whole document.
        self.name = name
        #: Default currency of the account. Mostly determines how amounts are displayed when viewing
        #: its entries listing.
        self.currency = currency
        #: :class:`AccountType` for this account.
        self.type = type
        #: External reference number (like, for example, a reference given by a bank). Used to
        #: uniquely match an account in moneyGuru to one being imported from another source.
        self.reference = None
        #: :class:`Group` in which this account belongs. Can be ``None`` (no group).
        self.group = None
        #: Unique account identifier. Can be used instead of the account name in the UI (faster than
        #: typing the name if you know your numbers).
        self.account_number = ''
        #: Inactive accounts don't show up in auto-complete.
        self.inactive = False
        #: Freeform notes about the account.
        self.notes = ''
        #: *readonly*. :class:`.EntryList` belonging to that account. This list is computed from
        #: :attr:`.Document.transactions` by the :class:`.Oven`.
        self.entries = EntryList(self)

    def __repr__(self):
        return '<Account %r>' % self.name

    def __lt__(self, other):
        return sort_string(self.name) < sort_string(other.name)

    # --- Public
    def normalize_amount(self, amount):
        """Returns a "displayable" amount depending on our :attr:`type`.

        When an account is a liability or an income, all amounts that we consider as increasing the
        liability or the income are in fact negative amounts (accounting is a zero-sum game,
        remember?). Therefore, if we add 10$ to a debt, our split will in fact be ``-10``. If we
        want to display a sheet showing entries affecting a liability or an income, we'll probably
        want to invert their sign, which is what this method does.

        In short, returns ``-amount`` if the account in a liability or an income.
        """
        return -amount if self.is_credit_account() else amount

    def is_balance_sheet_account(self):
        """Returns whether the account is an asset or liability."""
        return self.type in (AccountType.Asset, AccountType.Liability)

    def is_credit_account(self):
        """Returns whether the account is a liability or income."""
        return self.type in (AccountType.Liability, AccountType.Income)

    def is_debit_account(self):
        """Returns whether the account is an asset or expense."""
        return self.type in (AccountType.Asset, AccountType.Expense)

    def is_income_statement_account(self):
        """Returns whether the account is an income or expense."""
        return self.type in (AccountType.Income, AccountType.Expense)

    # --- Properties
    @property
    def combined_display(self):
        """*readonly*. Display name for the account.

        If it has an account number, prefix the name with the number.
        """
        if self.account_number:
            return "{0} - {1}".format(self.account_number, self.name)
        else:
            return self.name


class Group:
    """A group of :class:`Account`.

    Initialization argument simply set initial values for their relevant attributes, :attr:`name`,
    and :attr:`type`.
    """
    def __init__(self, name, type):
        #: Name of the group. Must be unique in the whole document.
        self.name = name
        #: :class:`AccountType` for this group.
        self.type = type
        self.expanded = False

    def __repr__(self):
        return '<Group %s>' % self.name

    def __lt__(self, other):
        return sort_string(self.name) < sort_string(other.name)


def new_name(base_name, search_func):
    name = base_name
    index = 0
    while search_func(name) is not None:
        index += 1
        name = '%s %d' % (base_name, index)
    return name

class AccountList(list):
    """Manages the list of :class:`Account` in a document.

    Mostly, ensures that name uniqueness is enforced, manages name clashes on new account creation.

    ``default_currency`` is the currency that we want new accounts (created in :meth:`find`) to
    have.

    Subclasses ``list``.
    """
    def __init__(self, default_currency):
        list.__init__(self)
        self.default_currency = default_currency
        self.auto_created = set()

    def add(self, account):
        """Adds ``account`` to the list.

        Does nothing if its :attr:`Account.reference` is already present in the list.
        """
        if self.find_reference(account.reference) is None:
            list.append(self, account)

    def clear(self):
        """Removes all elements from the list."""
        del self[:]

    def filter(self, group=NOT_GIVEN, type=NOT_GIVEN):
        """Returns all accounts of the given ``type`` and/or ``group``.

        :param group: :class:`Group`
        :param type: :class:`AccountType`
        """
        result = self
        if group is not NOT_GIVEN:
            result = (a for a in result if a.group == group)
        if type is not NOT_GIVEN:
            result = (a for a in result if a.type == type)
        return list(result)

    def find(self, name, auto_create_type=None):
        """Returns the first account matching with ``name`` (case insensitive)

        If ``auto_create_type`` is not ``None`` and no account is found, create an account of type
        ``auto_create_type`` and return it.
        """
        normalized = name.lower().strip()
        for account in self:
            if account.name.lower().strip() == normalized:
                return account
            elif account.account_number and normalized.startswith(account.account_number):
                return account
        if auto_create_type:
            account = Account(name.strip(), self.default_currency, type=auto_create_type)
            self.add(account)
            self.auto_created.add(account)
            return account

    def find_reference(self, reference):
        """Returns the account with ``reference`` or ``None`` if it isn't there."""
        if reference is None:
            return None
        for account in self:
            if account.reference == reference:
                return account

    def has_multiple_currencies(self):
        """Returns whether there's at least one account with a different currency.

        ... that is, a currency other than ``default_currency``.
        """
        return any(a.currency != self.default_currency for a in self)

    def new_name(self, base_name):
        """Returns a unique name from ``base_name``.

        If ``base_name`` already exists, append an incrementing number to it until we find a unique
        name.
        """
        return new_name(base_name, self.find)

    def remove(self, account):
        """Removes ``account`` from the list."""
        list.remove(self, account)
        self.auto_created.discard(account)

    def set_account_name(self, account, new_name):
        """Rename ``account`` to ``new_name``.

        If this new name already exists in the list, ``DuplicateAccountNameError`` is raised.
        """
        if not new_name:
            return
        other = self.find(new_name)
        if (other is not None) and (other is not account):
            raise DuplicateAccountNameError()
        account.name = new_name.strip()


class GroupList(list):
    """Manages the list of :class:`Group` in a document.

    Mostly, ensures that name uniqueness is enforced, manages name clashes on new group creation.

    Unlike with accounts, group names are not unique to the whole document, but only within an
    account type. Therefore, there can be an asset group with the same name as a liability group.

    Subclasses ``list``.
    """
    def clear(self):
        """Removes all elements from the list."""
        del self[:]

    def filter(self, type=NOT_GIVEN):
        """Returns all accounts of the given ``type``.

        :param type: :class:`AccountType`
        """
        result = self
        if type is not NOT_GIVEN:
            result = (g for g in result if g.type == type)
        return list(result)

    def find(self, name, base_type):
        """Returns the first account matching with ``name`` (case insensitive) within ``base_type``.

        :param name: ``str``
        :param base_type: :class:`AccountType`.
        """
        lowered = name.lower()
        for item in self:
            if item.name.lower() == lowered and item.type == base_type:
                return item

    def new_name(self, base_name, base_type):
        """Returns a unique name from ``base_name``.

        If ``base_name`` already exists, append an incrementing number to it until we find a unique
        name.

        We need to specify ``base_type`` because the uniqueness of a group name is only within an
        account type. So we need to know within which type we check uniqueness.
        """
        return new_name(base_name, partial(self.find, base_type=base_type))

    def set_group_name(self, group, newname):
        """Rename ``group`` to ``newname``.

        If this new name already exists in the list, ``DuplicateAccountNameError`` is raised.
        """
        other = self.find(newname, group.type)
        if (other is not None) and (other is not group):
            raise DuplicateAccountNameError()
        group.name = newname

