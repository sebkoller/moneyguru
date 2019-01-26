# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from io import BytesIO
from datetime import date

import pytest
from pytest import raises
from ..testutil import eq_

from ..base import testdata, Amount
from ...exception import FileFormatError
from ...loader import native
from ...const import AccountType
from ...model.currency import Currencies


@pytest.fixture
def loader():
    return native.Loader('USD')

def test_parse_non_xml(loader):
    content = b'this is not xml content'
    with raises(FileFormatError):
        loader._parse(BytesIO(content))

def test_parse_wrong_root_name(loader):
    content = b'<foobar></foobar>'
    with raises(FileFormatError):
        loader._parse(BytesIO(content))

def test_parse_minimal(loader):
    content = b'<moneyguru-file></moneyguru-file>'
    try:
        loader._parse(BytesIO(content))
    except FileFormatError:
        assert False

def test_wrong_date(loader):
    # these used to raise FileFormatError, but now, we just want to make sure that there is no
    # crash.
    content = b'<moneyguru-file><transaction date="bobsleigh" /></moneyguru-file>'
    loader._parse(BytesIO(content))
    loader.load() # no crash

def test_wrong_mtime(loader):
    # these used to raise FileFormatError, but now, we just want to make sure that there is no
    # crash.
    content = b'<moneyguru-file><transaction date="2008-01-01" mtime="abc" /></moneyguru-file>'
    loader._parse(BytesIO(content))
    loader.load() # no crash

def test_account_and_entry_values(loader):
    # Make sure loaded values are correct.
    Currencies.register('PLN', 'PLN')
    loader.parse(testdata.filepath('moneyguru', 'simple.moneyguru'))
    loader.load()
    accounts = list(loader.accounts)
    eq_(len(accounts), 3)
    account = accounts[0]
    eq_(account.name, 'Account 1')
    eq_(account.currency, 'USD')
    account = accounts[1]
    eq_(account.name, 'Account 2')
    eq_(account.currency, 'PLN')
    account = accounts[2]
    eq_(account.name, 'foobar')
    eq_(account.currency, 'USD')
    eq_(account.type, AccountType.Expense)
    transactions = list(loader.transactions)
    eq_(len(transactions), 4)
    transaction = transactions[0]
    eq_(len(transaction.splits), 2)
    eq_(transaction.date, date(2008, 2, 12))
    eq_(transaction.description, 'Entry 3')
    eq_(transaction.splits[1].account, None)
    eq_(transaction.mtime, 1203095473)
    split = transaction.splits[0]
    eq_(split.account.name, 'Account 2')
    eq_(split.amount, Amount(89, 'PLN'))

    transaction = transactions[1]
    eq_(transaction.date, date(2008, 2, 15))
    eq_(transaction.description, 'Entry 1')
    eq_(transaction.mtime, 1203095441)
    eq_(len(transaction.splits), 2)
    split = transaction.splits[0]
    eq_(split.account.name, 'Account 1')
    eq_(split.amount, Amount(42, 'USD'))
    split = transaction.splits[1]
    eq_(split.account.name, 'foobar')
    eq_(split.amount, Amount(-42, 'USD'))

    transaction = transactions[2]
    eq_(len(transaction.splits), 2)
    eq_(transaction.date, date(2008, 2, 16))
    eq_(transaction.description, 'Entry 2')
    eq_(transaction.payee, 'Some Payee')
    eq_(transaction.checkno, '42')
    eq_(transaction.splits[1].account, None)
    eq_(transaction.mtime, 1203095456)
    split = transaction.splits[0]
    eq_(split.account.name, 'Account 1')
    eq_(split.amount, Amount(-14, 'USD'))

    transaction = transactions[3]
    eq_(transaction.date, date(2008, 2, 19))
    eq_(transaction.description, 'Entry 4')
    eq_(transaction.splits[1].account, None)
    eq_(transaction.mtime, 1203095497)
    split = transaction.splits[0]
    eq_(split.account.name, 'Account 2')
    eq_(split.amount, Amount(-101, 'PLN'))

def test_unsupported_currency(loader):
    # Trying to load a file containing amounts of unsupported currencies raises FileFormatError
    loader.parse(testdata.filepath('moneyguru', 'unsupported_currency.moneyguru'))
    with raises(FileFormatError):
        loader.load()

