# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import datetime
import logging
import re

from core.util import dedupe, nonone
from core.trans import tr

from ..const import AccountType
from ..exception import FileFormatError
from ..model._ccore import (
    AccountList, TransactionList, UnsupportedCurrencyError, amount_parse, Transaction)
from ..model.currency import Currencies
from ..model.oven import Oven

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

def parse_amount(string, currency, **kwargs):
    try:
        return amount_parse(
            string, currency, with_expression=False, **kwargs)
    except UnsupportedCurrencyError:
        msg = tr(
            "Unsupported currency: {}. Aborting load. Did you disable a currency plugin?"
        ).format(currency)
        raise FileFormatError(msg)

def get_account_type(type):
    if type in AccountType.All:
        return type
    else:
        return AccountType.Asset

def get_account(accounts, accountname, auto_create_type):
    if accountname:
        account = accounts.find(accountname)
        if account is None:
            auto_create_type = get_account_type(auto_create_type)
            account = accounts.create(
                accountname, accounts.default_currency, auto_create_type)
    else:
        account = None
    return account

def process_split(accounts, accountname, str_amount, currency=None, strict_currency=False):
    # this amount is just to determine the auto_create_type
    if currency:
        str_amount += currency
    amount = parse_amount(str_amount, accounts.default_currency, strict_currency=strict_currency)
    auto_create_type = AccountType.Income if amount >= 0 else AccountType.Expense
    account = get_account(accounts, accountname, auto_create_type)
    currency = account.currency if account is not None else accounts.default_currency
    amount = parse_amount(str_amount, currency, strict_currency=strict_currency)
    return account, amount

def clean_date(str_date):
    # return str_date without garbage around (such as timestamps) or None if impossible
    match = re_possibly_a_date.search(str_date)
    return match.group() if match is not None else None

def guess_date_format(str_dates, formats_to_try):
    for format in dedupe(formats_to_try):
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

def parse_date_str(date_str, date_format):
    """Parses date_str using date_format and perform heuristic fixes if needed.
    """
    result = datetime.datetime.strptime(date_str, date_format).date()
    if result.year < 1900:
        # we have a typo in the house. Just use 2000 + last-two-digits
        year = (result.year % 100) + 2000
        result = result.replace(year=year)
    return result

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

    def __init__(self, default_currency, default_date_format=None):
        self.default_currency = default_currency
        self.default_date_format = default_date_format
        self.accounts = AccountList(default_currency)
        self.transactions = TransactionList()
        self.oven = Oven(self.accounts, self.transactions, None, None)
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
    def guess_date_format(self, str_dates):
        totry = DATE_FORMATS
        extra = []
        if self.NATIVE_DATE_FORMAT:
            extra.append(self.NATIVE_DATE_FORMAT)
        if self.EXTRA_DATE_FORMATS:
            extra += self.EXTRA_DATE_FORMATS
        if self.default_date_format:
            extra.append(self.default_date_format)
        return guess_date_format(str_dates, extra + totry)

    def get_currency(self, code):
        try:
            if code and Currencies.has(code):
                return code
        except ValueError:
            pass
        return self.default_currency

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

    def load(self):
        """Loads the parsed info into self.accounts and self.transactions.

        You must have called parse() before calling this.
        """
        self._load()
        self._post_load()
        self.oven.cook(datetime.date.min, until_date=None)
        self._fetch_currencies()

class TransactionInfo:
    def __init__(self):
        self.date = None
        self.description = None
        self.payee = None
        self.checkno = None
        self.account = None
        self.transfer = None
        self.amount = None
        self.currency = None
        self.reference = None # will be applied to all splits
        self.splits = []

    def is_valid(self):
        return bool(self.date and ((self.account and self.amount) or self.splits))

    def load(self, accounts):
        description = self.description
        payee = self.payee
        checkno = self.checkno
        date = self.date
        account = amount = None
        if self.account:
            account, amount = process_split(accounts, self.account, self.amount, self.currency)
        transaction = Transaction(1, date, description, payee, checkno, account, amount)
        for str_account, str_amount, memo in self.splits:
            account, amount = process_split(
                accounts, str_account, str_amount, None)
            # splits are only used for QIF and in QIF, amounts are reversed
            amount *= -1
            memo = nonone(memo, '')
            split = transaction.new_split()
            split.account = account
            split.amount = amount
            split.memo = memo
        while len(transaction.splits) < 2:
            transaction.new_split()
        transaction.balance()
        if self.reference is not None:
            for split in transaction.splits:
                if split.reference is None:
                    split.reference = self.reference
        return transaction

    def add_split(self, account, amount, memo):
        self.splits.append((account, amount, memo))
