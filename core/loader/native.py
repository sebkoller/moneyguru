# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import xml.etree.cElementTree as ET

from core.util import tryint, nonone

from ..exception import FileFormatError
from ..model._ccore import Transaction
from ..model.budget import Budget, BudgetList
from ..model.oven import Oven
from ..model.recurrence import Recurrence, Spawn
from . import base


def parse_amount(string, currency):
    return base.parse_amount(string, currency, strict_currency=True)

class Loader(base.Loader):
    FILE_OPEN_MODE = 'rb'
    NATIVE_DATE_FORMAT = '%Y-%m-%d'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # I did not manage to create a repeatable test for it, but self.schedules has to be ordered
        # because the order in which the spawns are created must stay the same
        self.schedules = []
        self.budgets = BudgetList()
        self.oven = Oven(self.accounts, self.transactions, self.schedules, self.budgets)
        self.properties = {}
        self.document_id = None

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
                return base.parse_date_str(s, self.parsing_date_format)
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

        def read_transaction_element(element):
            attrib = element.attrib
            date = str2date(attrib.get('date'), TODAY)
            description = attrib.get('description')
            payee = attrib.get('payee')
            checkno = attrib.get('checkno')
            txn = Transaction(1, date, description, payee, checkno, None, None)
            txn.notes = handle_newlines(attrib.get('notes')) or ''
            try:
                txn.mtime = int(attrib.get('mtime', 0))
            except ValueError:
                txn.mtime = 0
            reference = attrib.get('reference')
            for split_element in element.iter('split'):
                attrib = split_element.attrib
                accountname = attrib.get('account')
                str_amount = attrib.get('amount')
                account, amount = base.process_split(
                    self.accounts, accountname, str_amount, strict_currency=True)
                split = txn.new_split()
                split.account = account
                split.amount = amount
                split.memo = attrib.get('memo') or ''
                split.reference = attrib.get('reference') or reference
                if attrib.get('reconciled') == 'y':
                    split.reconciliation_date = date
                elif account is None or not (not amount or amount.currency_code == account.currency):
                    # fix #442: off-currency transactions shouldn't be reconciled
                    split.reconciliation_date = None
                elif 'reconciliation_date' in attrib:
                    split.reconciliation_date = str2date(attrib['reconciliation_date'])
            txn.balance()
            while len(txn.splits) < 2:
                txn.new_split()
            return txn

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
            attrib = account_element.attrib
            name = attrib.get('name')
            if not name:
                continue
            currency = self.get_currency(attrib.get('currency'))
            type = base.get_account_type(attrib.get('type'))
            account = self.accounts.create(name, currency, type)
            group = attrib.get('group')
            reference = attrib.get('reference')
            account_number = attrib.get('account_number', '')
            inactive = attrib.get('inactive') == 'y'
            notes = handle_newlines(attrib.get('notes', ''))
            account.change(
                groupname=group, reference=reference,
                account_number=account_number, inactive=inactive, notes=notes)
        elements = [e for e in root if e.tag == 'transaction'] # we only want transaction element *at the root*
        for transaction_element in elements:
            txn = read_transaction_element(transaction_element)
            self.transactions.add(txn)
        for recurrence_element in root.iter('recurrence'):
            attrib = recurrence_element.attrib
            ref = read_transaction_element(recurrence_element.find('transaction'))
            repeat_type = attrib.get('type')
            repeat_every = int(attrib.get('every', '1'))
            recurrence = Recurrence(ref, repeat_type, repeat_every)
            recurrence.stop_date = str2date(attrib.get('stop_date'))
            for exception_element in recurrence_element.iter('exception'):
                try:
                    date = str2date(exception_element.attrib['date'])
                    txn_element = exception_element.find('transaction')
                    exception = read_transaction_element(txn_element) if txn_element is not None else None
                    if exception:
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
                    change = read_transaction_element(txn_element) if txn_element is not None else None
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
            amount = parse_amount(amount, account.currency)
            budget = Budget(account, amount)
            budget.notes = nonone(notes, '')
            self.budgets.append(budget)
