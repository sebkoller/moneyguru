# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import trget
from .column import Column
from ..model.sort import ACCOUNT_SORT_KEY
from .table import Row
from .entry_table_base import EntryTableBase, EntryTableRow, TotalRow, PreviousBalanceRow

trcol = trget('columns')

class AccountRow(Row):
    def __init__(self, table, account):
        Row.__init__(self, table)
        self.account = account
        self.account_name = account.name


class GeneralLedgerRow(EntryTableRow):
    @property
    def balance(self):
        if self.account.is_balance_sheet_account():
            return EntryTableRow.balance.fget(self)
        else:
            return ''


class GeneralLedgerTable(EntryTableBase):
    SAVENAME = 'GeneralLedgerTable'
    COLUMNS = [
        Column('status', display=''),
        Column('date', display=trcol("Date")),
        Column('reconciliation_date', display=trcol("Reconciliation Date"), visible=False, optional=True),
        Column('checkno', display=trcol("Check #"), visible=False, optional=True),
        Column('description', display=trcol("Description"), optional=True),
        Column('payee', display=trcol("Payee"), visible=False, optional=True),
        Column('transfer', display=trcol("Transfer")),
        Column('debit', display=trcol("Debit")),
        Column('credit', display=trcol("Credit")),
        Column('balance', display=trcol("Balance")),
    ]
    ENTRY_ROWCLASS = GeneralLedgerRow

    # --- Override
    def _fill(self):
        accounts = sorted(self.document.accounts, key=ACCOUNT_SORT_KEY)
        for account in accounts:
            rows = self._get_account_rows(account)
            if not rows:
                continue
            self.append(AccountRow(self, account))
            for row in rows:
                self.append(row)

    def _get_current_account(self):
        row = self.selected_row
        return row.account if row is not None else None

    def _get_totals_currency(self):
        return self.document.default_currency

    # --- Public
    def is_account_row(self, row):
        return isinstance(row, AccountRow)

    def is_bold_row(self, row):
        return isinstance(row, (TotalRow, PreviousBalanceRow))
