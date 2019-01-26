# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import logging
import re

from core.util import nonone, dedupe
from core.trans import tr

from ..const import AccountType
from ..exception import FileFormatError
from ..model._ccore import (
    AccountList, TransactionList, UnsupportedCurrencyError, amount_parse)
from ..model.currency import Currencies
from ..model.oven import Oven
from ..model.transaction import Transaction

# date formats to use for format guessing
# there is not one test for each single format
# The order of the fields depending on the separator is different because we try to minimize the
# possibility of errors. Most american users use the slash separator with month as a first field
# and most european users have dot or hyphen seps with the first field being the day.

BASE_DATE_FORMATS = [
    '%m/%d/%y', '%m/%d/%Y', '%d/%m/%Y', '%d/%m/%y', '%Y/%m/%d', '%d/%b/%Y', '%d/%b/%y'
]
EXTRA_DATE_SEPS = ['.', '-', ' ']
DATE_FORMATS = BASE_DATE_FORMATS[:]
# Re-add all date formats with their separator replaced
for sep in EXTRA_DATE_SEPS:
    for base_format in BASE_DATE_FORMATS:
        DATE_FORMATS.append(base_format.replace('/', sep))
# Finally, add special formats
DATE_FORMATS += ['%m/%d\'%y', '%Y%m%d']

POSSIBLE_PATTERNS = [
    r'[\d/.\- ]{6,10}',
    r'\d{1,2}[/.\- ]\w{3}[/.\- ]\d{2,4}',
    r"\d{1,2}/\d{1,2}'\d{2,4}",
]
re_possibly_a_date = re.compile('|'.join(POSSIBLE_PATTERNS))

class Loader:
    """Base interface for loading files containing financial information to load into moneyGuru.

    To use it, just call load() and then fetch the accounts & transactions. This information is in
    the form of lists of dicts. The transactions are sorted in order of date.
    """
    FILE_OPEN_MODE = 'rt'
    FILE_ENCODING = 'utf-8'
    # Native date format is a format native to the file type. It doesn't necessarily means that it's
    # the only possible date format in it, but it's the one that will be tried first when guessing
    # (before the default date format). If guessing never occurs, it will be the parsing date format.
    # This format is a sys format (%-based)
    NATIVE_DATE_FORMAT = None
    # Some extra date formats to try before standard date guessing order
    EXTRA_DATE_FORMATS = None
    # Whether we fail with a ``FileFormatError`` when encountering an unsupported currency or we
    # fall back to the default currency
    STRICT_CURRENCY = False

    def __init__(self, default_currency, default_date_format=None):
        self.default_currency = default_currency
        self.default_date_format = default_date_format
        self.accounts = AccountList(default_currency)
        self.transactions = TransactionList()
        self.oven = Oven(self.accounts, self.transactions, None, None)
        self.properties = {}
        self.target_account = None # when set, overrides the reference matching system
        self.recurrence_infos = []
        self.budget_infos = []
        self.account_info = AccountInfo()
        self.transaction_info = TransactionInfo()
        self.transaction_cancelled = False
        self.split_info = SplitInfo()
        self.document_id = None
        # The Loader subclass should set parsing_date_format to the format used (system-type) when
        # parsing dates. This format is used in the ImportWindow. It is also used in
        # self.parse_date_str as a default value
        self.parsing_date_format = self.NATIVE_DATE_FORMAT

    # --- Private
    def _fetch_currencies(self):
        # Fetch rates if needed
        start_date = min((t.date for t in self.transactions), default=datetime.date.max)
        currencies = {a.currency for a in self.accounts}
        for txn in self.transactions:
            for split in txn.splits:
                if split.amount:
                    currencies.add(split.amount.currency_code)
        Currencies.get_rates_db().ensure_rates(start_date, list(currencies))

    def _process_split_info(self, split_info):
        # this amount is just to determine the auto_create_type
        str_amount = split_info.amount
        if split_info.currency:
            str_amount += split_info.currency
        amount = self.parse_amount(str_amount, self.default_currency)
        auto_create_type = AccountType.Income if amount >= 0 else AccountType.Expense
        aname = split_info.account
        if aname:
            split_info.account = self.accounts.find(aname)
            if split_info.account is None:
                split_info.account = self.accounts.create(
                    aname, self.default_currency, auto_create_type)
        else:
            split_info.account = None
        currency = split_info.account.currency if split_info.account is not None else self.default_currency
        split_info.amount = self.parse_amount(str_amount, currency)

    # --- Virtual
    def _parse(self, infile):
        """Parse infile and raise FileFormatError if infile is not the right format. Don't bother
        with an exception message, app.MoneyGuru will re-raise it with a message if needed.
        """
        raise NotImplementedError()

    def _load(self):
        """Use the parsed info to fill the appropriate account/txn info with the start_* and flush_*
        methods.
        """
        raise NotImplementedError()

    def _post_load(self):
        """Perform post load processing, such as duplicate removal
        """
        pass

    # --- Protected
    def clean_date(self, str_date):
        # return str_date without garbage around (such as timestamps) or None if impossible
        match = re_possibly_a_date.search(str_date)
        return match.group() if match is not None else None

    def guess_date_format(self, str_dates):
        totry = DATE_FORMATS[:]
        extra = []
        if self.NATIVE_DATE_FORMAT:
            extra.append(self.NATIVE_DATE_FORMAT)
        if self.EXTRA_DATE_FORMATS:
            extra += self.EXTRA_DATE_FORMATS
        if self.default_date_format:
            extra.append(self.default_date_format)
        for format in dedupe(extra + totry):
            found_at_least_one = False
            for str_date in str_dates:
                try:
                    datetime.datetime.strptime(str_date, format)
                    found_at_least_one = True
                except ValueError:
                    logging.debug("Failed try to read the date %s with the format %s", str_date, format)
                    break
            else:
                if found_at_least_one:
                    logging.debug("Correct date format: %s", format)
                    return format
        return None

    def parse_date_str(self, date_str, date_format=None):
        """Parses date_str using date_format and perform heuristic fixes if needed.
        """
        if not date_format:
            date_format = self.parsing_date_format
        result = datetime.datetime.strptime(date_str, date_format).date()
        if result.year < 1900:
            # we have a typo in the house. Just use 2000 + last-two-digits
            year = (result.year % 100) + 2000
            result = result.replace(year=year)
        return result

    def start_account(self):
        self.flush_account() # Implicit

    def flush_account(self):
        self.flush_transaction()
        if self.account_info.is_valid():
            info = self.account_info
            account_type = info.type
            if account_type not in AccountType.All:
                account_type = AccountType.Asset
            account_currency = self.default_currency
            try:
                if info.currency and Currencies.has(info.currency):
                    account_currency = info.currency
            except ValueError:
                pass # keep account_currency as self.default_currency
            account = self.accounts.find(info.name)
            if account is None:
                account = self.accounts.create(
                    info.name, account_currency, account_type)
            else:
                # Already auto-created by a transaction. override type and
                # currency
                account.change(type=account_type, currency=account_currency)
            if info.group:
                account.change(groupname=info.group)
            account.change(
                reference=info.reference, account_number=info.account_number,
                inactive=info.inactive, notes=info.notes)
        self.account_info = AccountInfo()

    def cancel_account(self):
        self.account_info = AccountInfo()
        self.transaction_info = TransactionInfo()
        self.split_info = SplitInfo()

    def start_transaction(self):
        self.flush_transaction() # Implicit

    def flush_transaction(self):
        """If called between a start_account and flush_account call, ACCOUNT is automatically set"""
        self.flush_split()
        if not self.transaction_cancelled:
            info = self.transaction_info
            if info.account is None and self.account_info and self.account_info.name:
                info.account = self.account_info.name
            if info.is_valid():
                split_accounts = [s.account for s in info.splits]
                if info.account and info.account not in split_accounts:
                    info.splits.insert(0, SplitInfo(info.account, info.amount, info.currency, False))
                if info.transfer and info.transfer not in split_accounts:
                    info.splits.append(SplitInfo(info.transfer, info.amount, info.currency, True))
                for split_info in info.splits:
                    self._process_split_info(split_info)
                transaction = info.load()
                self.transactions.add(transaction)
        self.transaction_cancelled = False
        self.transaction_info = TransactionInfo()

    def cancel_transaction(self):
        self.transaction_cancelled = True

    def flush_split(self):
        if self.split_info.is_valid():
            self.transaction_info.splits.append(self.split_info)
        self.split_info = SplitInfo()

    # --- Public
    def parse(self, filename):
        """Parses 'filename' and raises FileFormatError if appropriate."""
        try:
            if 't' in self.FILE_OPEN_MODE:
                kw = {'encoding': self.FILE_ENCODING, 'errors': 'ignore'}
            else:
                kw = {}
            with open(filename, self.FILE_OPEN_MODE, **kw) as infile:
                self._parse(infile)
        except IOError:
            raise FileFormatError()

    @classmethod
    def parse_amount(cls, string, currency):
        try:
            return amount_parse(
                string, currency, with_expression=False,
                strict_currency=cls.STRICT_CURRENCY
            )
        except UnsupportedCurrencyError:
            msg = tr(
                "Unsupported currency: {}. Aborting load. Did you disable a currency plugin?"
            ).format(currency)
            raise FileFormatError(msg)

    def load(self):
        """Loads the parsed info into self.accounts and self.transactions.

        You must have called parse() before calling this.
        """
        self._load()
        self.flush_account() # Implicit
        self._post_load()
        self.oven.cook(datetime.date.min, until_date=None)
        self._fetch_currencies()


class AccountInfo:
    def __init__(self):
        self.name = None
        self.currency = None
        self.type = AccountType.Asset
        self.group = None
        self.budget = None
        self.budget_target = None
        self.reference = None
        self.account_number = ''
        self.inactive = False
        self.notes = ''

    def __repr__(self):
        return '<AccountInfo: %s>' % self.name

    def is_valid(self):
        return bool(self.name)


class TransactionInfo:
    def __init__(self):
        self.date = None
        self.description = None
        self.payee = None
        self.checkno = None
        self.notes = None
        self.account = None
        self.transfer = None
        self.amount = None
        self.currency = None
        self.reference = None # will be applied to all splits
        self.mtime = 0
        self.splits = []

    def is_valid(self):
        return bool(self.date and ((self.account and self.amount) or self.splits))

    def load(self):
        description = self.description
        payee = self.payee
        checkno = self.checkno
        date = self.date
        transaction = Transaction(date, description, payee, checkno)
        transaction.notes = nonone(self.notes, '')
        for split_info in self.splits:
            account = split_info.account
            amount = split_info.amount
            if split_info.amount_reversed:
                amount = -amount
            memo = nonone(split_info.memo, '')
            split = transaction.new_split()
            split.account = account
            split.amount = amount
            split.memo = memo
            if account is None or not (not amount or amount.currency_code == account.currency):
                # fix #442: off-currency transactions shouldn't be reconciled
                split.reconciliation_date = None
            elif split_info.reconciliation_date is not None:
                split.reconciliation_date = split_info.reconciliation_date
            elif split_info.reconciled: # legacy
                split.reconciliation_date = transaction.date
            split.reference = split_info.reference
        while len(transaction.splits) < 2:
            transaction.new_split()
        transaction.balance()
        transaction.mtime = self.mtime
        if self.reference is not None:
            for split in transaction.splits:
                if split.reference is None:
                    split.reference = self.reference
        return transaction


class SplitInfo:
    def __init__(self, account=None, amount=None, currency=None, amount_reversed=False):
        self.account = account
        self.amount = amount
        self.currency = currency
        self.memo = None
        self.reconciled = False
        self.reconciliation_date = None
        self.reference = None
        self.amount_reversed = amount_reversed

    def __repr__(self):
        return '<SplitInfo %r %r>' % (self.account, self.amount)

    def is_valid(self):
        return self.amount is not None
