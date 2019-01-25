# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

class Const:
    def __init__(self, repr):
        self.repr = repr

    def __repr__(self):
        return self.repr

    __str__ = __repr__

NOEDIT = Const("NOEDIT")

DATE_FORMAT_FOR_PREFERENCES = '%d/%m/%Y'

# These constants are in sync with the GUI
class PaneType:
    NetWorth = 0
    Profit = 1
    Transaction = 2
    Account = 3
    Schedule = 4
    Budget = 5
    GeneralLedger = 7
    DocProps = 8
    PluginList = 9
    Empty = 100
    Plugin = 1000
    ReadOnlyTablePlugin = 1001

# These constants are in sync with the GUI
class PaneArea:
    Main = 1
    BottomGraph = 2
    RightChart = 3

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

