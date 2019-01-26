# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from ..testutil import eq_

from ...loader import base

def test_accounts():
    loader = base.Loader('USD')
    eq_(len(loader.accounts), 0)

def test_unnamed_account():
    # Name is mandatory.
    loader = base.Loader('USD')
    loader.start_account()
    loader.flush_account()
    eq_(len(loader.accounts), 0)

def test_default_currency():
    # Currency is optional.
    loader = base.Loader('USD')
    loader.start_account()
    loader.account_info.name = 'foo'
    loader.flush_account()
    eq_(len(loader.accounts), 1)
    assert list(loader.accounts)[0].currency == 'USD'

# --- One account
def loader_one_account():
    loader = base.Loader('USD')
    loader.start_account()
    loader.account_info.name = 'foo'
    return loader

def test_missing_amount():
    # Amount is mandatory.
    loader = loader_one_account()
    loader.start_transaction()
    loader.transaction_info.date = date(2008, 2, 15)
    loader.transaction_info.description = 'foo'
    loader.transaction_info.transfer = 'bar'
    loader.flush_account()
    eq_(len(loader.transactions), 0)

def test_missing_date():
    # Date is mandatory.
    loader = loader_one_account()
    loader.start_transaction()
    loader.transaction_info.amount = '42'
    loader.transaction_info.description = 'foo'
    loader.transaction_info.transfer = 'bar'
    loader.flush_account()
    eq_(len(loader.transactions), 0)

def test_missing_description():
    # Description is optional.
    loader = loader_one_account()
    loader.start_transaction()
    loader.transaction_info.date = date(2008, 2, 15)
    loader.transaction_info.amount = '42'
    loader.transaction_info.transfer = 'bar'
    loader.flush_account()
    eq_(len(loader.transactions), 1)

def test_missing_transfer():
    # Category is optional.
    loader = loader_one_account()
    loader.start_transaction()
    loader.transaction_info.date = date(2008, 2, 15)
    loader.transaction_info.amount = '42'
    loader.transaction_info.description = 'foo'
    loader.flush_account()
    eq_(len(loader.transactions), 1)
    # But the balancing entry in the imbalance account
    eq_(len(loader.accounts), 1)
