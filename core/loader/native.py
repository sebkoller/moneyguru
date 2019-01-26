# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import xml.etree.cElementTree as ET

from core.util import tryint, stripfalse, nonone

from ..exception import FileFormatError
from ..model.budget import Budget, BudgetList
from ..model.oven import Oven
from ..model.recurrence import Recurrence, Spawn
from .base import SplitInfo, TransactionInfo
from . import base

class RecurrenceInfo:
    def __init__(self):
        self.repeat_type = None
        self.repeat_every = 1
        self.stop_date = None
        self.date2exception = {}
        self.date2globalchange = {}
        self.transaction_info = TransactionInfo()

    def is_valid(self):
        return self.transaction_info.is_valid()


class BudgetInfo:
    def __init__(self, account=None, target=None, amount=None):
        self.account = account
        self.target = target
        self.amount = amount
        self.notes = None
        self.repeat_type = None
        self.repeat_every = None
        self.start_date = None

    def is_valid(self):
        return self.account and self.amount

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
        self.recurrence_info = RecurrenceInfo()
        self.budget_info = BudgetInfo()
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
            self.recurrence_info.repeat_type = attrib.get('type')
            self.recurrence_info.repeat_every = int(attrib.get('every', '1'))
            self.recurrence_info.stop_date = str2date(attrib.get('stop_date'))
            read_transaction_element(recurrence_element.find('transaction'), self.recurrence_info.transaction_info)
            for exception_element in recurrence_element.iter('exception'):
                try:
                    date = str2date(exception_element.attrib['date'])
                    txn_element = exception_element.find('transaction')
                    txn = read_transaction_element(txn_element, TransactionInfo()) if txn_element is not None else None
                    self.recurrence_info.date2exception[date] = txn
                except KeyError:
                    continue
            for change_element in recurrence_element.iter('change'):
                try:
                    date = str2date(change_element.attrib['date'])
                    txn_element = change_element.find('transaction')
                    txn = read_transaction_element(txn_element, TransactionInfo()) if txn_element is not None else None
                    self.recurrence_info.date2globalchange[date] = txn
                except KeyError:
                    continue
            self.flush_recurrence()
        for budget_element in root.iter('budget'):
            attrib = budget_element.attrib
            self.budget_info.account = attrib.get('account')
            self.budget_info.repeat_type = attrib.get('type')
            self.budget_info.repeat_every = tryint(attrib.get('every'), default=None)
            self.budget_info.amount = attrib.get('amount')
            self.budget_info.notes = attrib.get('notes')
            self.budget_info.start_date = str2date(attrib.get('start_date'))
            self.flush_budget()

    def load(self):
        self._load()
        self.flush_account() # Implicit
        # Scheduled
        for info in self.recurrence_infos:
            all_txn = [info.transaction_info] +\
                list(stripfalse(info.date2exception.values())) +\
                list(info.date2globalchange.values())
            for txn_info in all_txn:
                for split_info in txn_info.splits:
                    self._process_split_info(split_info)
            ref = info.transaction_info.load()
            recurrence = Recurrence(ref, info.repeat_type, info.repeat_every)
            recurrence.stop_date = info.stop_date
            for date, transaction_info in info.date2exception.items():
                if transaction_info is not None:
                    exception = transaction_info.load()
                    spawn = Spawn(recurrence, exception, date, exception.date)
                    recurrence.date2exception[date] = spawn
                else:
                    recurrence.delete_at(date)
            for date, transaction_info in info.date2globalchange.items():
                change = transaction_info.load()
                spawn = Spawn(recurrence, change, date, change.date)
                recurrence.date2globalchange[date] = spawn
            self.schedules.append(recurrence)

        # Budgets
        if self.budget_infos:
            info = self.budget_infos[0]
            if info.start_date:
                self.budgets.start_date = info.start_date
            self.budgets.repeat_type = info.repeat_type
            if info.repeat_every:
                self.budgets.repeat_every = info.repeat_every
        for info in self.budget_infos:
            account = self.accounts.find(info.account)
            if account is None:
                continue
            amount = self.parse_amount(info.amount, account.currency)
            budget = Budget(account, amount)
            budget.notes = nonone(info.notes, '')
            self.budgets.append(budget)
        self._post_load()
        self.oven.cook(datetime.date.min, until_date=None)
        self._fetch_currencies()

    def flush_account(self):
        if self.account_info.is_valid() and self.account_info.budget:
            info = self.account_info
            self.budget_infos.append(BudgetInfo(info.name, info.budget))
        super().flush_account()

    def flush_recurrence(self):
        if self.recurrence_info.is_valid():
            self.recurrence_infos.append(self.recurrence_info)
        self.recurrence_info = RecurrenceInfo()

    def flush_budget(self):
        if self.budget_info.is_valid():
            self.budget_infos.append(self.budget_info)
        self.budget_info = BudgetInfo()

