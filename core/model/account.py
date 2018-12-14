# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from functools import partial

from .sort import sort_string
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

    def group_of_account(self, account):
        if account.groupname:
            return self.find(account.groupname, account.type)
        else:
            return None

    def new_name(self, base_name, base_type):
        """Returns a unique name from ``base_name``.

        If ``base_name`` already exists, append an incrementing number to it until we find a unique
        name.

        We need to specify ``base_type`` because the uniqueness of a group name is only within an
        account type. So we need to know within which type we check uniqueness.
        """
        return new_name(base_name, partial(self.find, base_type=base_type))
