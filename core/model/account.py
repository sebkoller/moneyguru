# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

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
