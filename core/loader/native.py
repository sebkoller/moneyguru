# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import xml.etree.cElementTree as ET

from core.util import tryint, nonone

from ..exception import FileFormatError
from ..model.budget import Budget, BudgetList
from ..model.oven import Oven
from ..model.recurrence import Recurrence, Spawn
from .base import SplitInfo, TransactionInfo
from . import base

class Loader(base.Loader):
    FILE_OPEN_MODE = 'rb'
    NATIVE_DATE_FORMAT = '%Y-%m-%d'
    STRICT_CURRENCY = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # I did not manage to create a repeatable test for it, but self.schedules has to be ordered
        # because the order in which the spawns are created must stay the same
        self.schedules = []
        self.budgets = BudgetList()
        self.oven = Oven(self.accounts, self.transactions, self.schedules, self.budgets)

    def _parse(self, infile):
        try:
            root = ET.parse(infile).getroot()
        except SyntaxError:
            raise FileFormatError()
        if root.tag != 'moneyguru-file':
            raise FileFormatError()
        self.root = root

    def _load(self):
        TODAY = datetime.date.today()

        def str2date(s, default=None):
            try:
                return self.parse_date_str(s)
            except (ValueError, TypeError):
                return default

        def handle_newlines(s):
            # etree doesn't correctly save newlines. During save, we escape them. Now's the time to
            # restore them.
            # XXX After a while, when most users will have used a moneyGuru version that doesn't
            # need newline escaping on save, we can remove this one as well.
            if not s:
                return s
            return s.replace('\\n', '\n')

        def read_transaction_element(element, info):
            attrib = element.attrib
            info.account = attrib.get('account')
            info.date = str2date(attrib.get('date'), TODAY)
            info.description = attrib.get('description')
            info.payee = attrib.get('payee')
            info.checkno = attrib.get('checkno')
            info.notes = handle_newlines(attrib.get('notes'))
            info.transfer = attrib.get('transfer')
            try:
                info.mtime = int(attrib.get('mtime', 0))
            except ValueError:
                info.mtime = 0
            info.reference = attrib.get('reference')
            for split_element in element.iter('split'):
                attrib = split_element.attrib
                split_info = SplitInfo()
                split_info.account = split_element.attrib.get('account')
                split_info.amount = split_element.attrib.get('amount')
                split_info.memo = split_element.attrib.get('memo')
                split_info.reference = split_element.attrib.get('reference')
                if 'reconciled' in split_element.attrib: # legacy
                    split_info.reconciled = split_element.attrib['reconciled'] == 'y'
                if 'reconciliation_date' in split_element.attrib:
                    split_info.reconciliation_date = str2date(split_element.attrib['reconciliation_date'])
                info.splits.append(split_info)
            return info

        root = self.root
        self.document_id = root.attrib.get('document_id')
        props_element = root.find('properties')
        if props_element is not None:
            for name, value in props_element.attrib.items():
                # For now, all our prefs except default_currency are ints, so
                # we can simply assume tryint, but we'll eventually need
                # something more sophisticated.
                if name != 'default_currency':
                    value = tryint(value, default=None)
                if name and value is not None:
                    self.properties[name] = value
        for account_element in root.iter('account'):
            self.start_account()
            attrib = account_element.attrib
            self.account_info.name = attrib.get('name')
            self.account_info.currency = attrib.get('currency')
            self.account_info.type = attrib.get('type')
            self.account_info.group = attrib.get('group')
            self.account_info.budget = attrib.get('budget')
            self.account_info.reference = attrib.get('reference')
            self.account_info.account_number = attrib.get('account_number', '')
            self.account_info.inactive = attrib.get('inactive') == 'y'
            self.account_info.notes = handle_newlines(attrib.get('notes', ''))
            self.flush_account()
        elements = [e for e in root if e.tag == 'transaction'] # we only want transaction element *at the root*
        for transaction_element in elements:
            self.start_transaction()
            read_transaction_element(transaction_element, self.transaction_info)
            self.flush_transaction()
        for recurrence_element in root.iter('recurrence'):
            attrib = recurrence_element.attrib
            txn_info = read_transaction_element(
                recurrence_element.find('transaction'), TransactionInfo())
            for split_info in txn_info.splits:
                self._process_split_info(split_info)
            ref = txn_info.load()
            repeat_type = attrib.get('type')
            repeat_every = int(attrib.get('every', '1'))
            recurrence = Recurrence(ref, repeat_type, repeat_every)
            recurrence.stop_date = str2date(attrib.get('stop_date'))
            for exception_element in recurrence_element.iter('exception'):
                try:
                    date = str2date(exception_element.attrib['date'])
                    txn_element = exception_element.find('transaction')
                    txn = read_transaction_element(txn_element, TransactionInfo()) if txn_element is not None else None
                    if txn:
                        for split_info in txn.splits:
                            self._process_split_info(split_info)
                        exception = txn.load()
                        spawn = Spawn(recurrence, exception, date, exception.date)
                        recurrence.date2exception[date] = spawn
                    else:
                        recurrence.delete_at(date)
                except KeyError:
                    continue
            for change_element in recurrence_element.iter('change'):
                try:
                    date = str2date(change_element.attrib['date'])
                    txn_element = change_element.find('transaction')
                    txn = read_transaction_element(txn_element, TransactionInfo()) if txn_element is not None else None
                    for split_info in txn.splits:
                        self._process_split_info(split_info)
                    change = txn.load()
                    spawn = Spawn(recurrence, change, date, change.date)
                    recurrence.date2globalchange[date] = spawn
                except KeyError:
                    continue
            self.schedules.append(recurrence)
        budgets = list(root.iter('budget'))
        if budgets:
            attrib = budgets[0].attrib
            start_date = str2date(attrib.get('start_date'))
            if start_date:
                self.budgets.start_date = start_date
            self.budgets.repeat_type = attrib.get('type')
            repeat_every = tryint(attrib.get('every'), default=None)
            if repeat_every:
                self.budgets.repeat_every = repeat_every
        for budget_element in budgets:
            attrib = budget_element.attrib
            account_name = attrib.get('account')
            amount = attrib.get('amount')
            notes = attrib.get('notes')
            if not (account_name and amount):
                continue
            account = self.accounts.find(account_name)
            if account is None:
                continue
            amount = self.parse_amount(amount, account.currency)
            budget = Budget(account, amount)
            budget.notes = nonone(notes, '')
            self.budgets.append(budget)
