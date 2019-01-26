# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from pytest import raises
from ..testutil import eq_

from ..base import testdata, Amount
from ...exception import FileFormatError
from ...loader import ofx

def test_dont_choke_on_empty_files():
    # The ofx loader doesn't choke on an empty file
    loader = ofx.Loader('USD')
    with raises(FileFormatError):
        loader.parse(testdata.filepath('zerofile'))

def test_format_error():
    loader = ofx.Loader('USD')
    with raises(FileFormatError):
        loader.parse(testdata.filepath('ofx', 'invalid.ofx'))

def test_amounts_in_invalid_currency_account():
    loader = ofx.Loader('USD')
    loader.parse(testdata.filepath('ofx', 'invalid_currency.ofx'))
    loader.load()
    account = loader.accounts.find('815-30219-11111-EOP')
    entries = loader.accounts.entries_for_account(account)
    eq_(len(entries), 3)
    entry = next(iter(entries))
    eq_(entry.amount, Amount(0.02, 'USD'))

def test_blank_line_ofx_attrs():
    # Just make sure that a ofx file starting with a blank line is correctly loaded
    loader = ofx.Loader('USD')
    loader.parse(testdata.filepath('ofx', 'blank_first_line.ofx'))
    loader.load()
    eq_(len(loader.accounts), 1)
    eq_(len(loader.transactions), 5)

def test_qfx():
    # I have never seen a real QFX file, but according to #423, it's the same
    # as OFX with a different header, so I took desjardins.ofx, replaced the
    # header called it a day. Might be awfully wrong, but it's still better
    # than nothing...
    loader = ofx.Loader('USD')
    loader.parse(testdata.filepath('ofx', 'desjardins.qfx'))
    loader.load()
    eq_(len(loader.accounts), 3)
    eq_(len(loader.accounts), 3)

# ---
def loader_desjardins():
    loader = ofx.Loader('USD')
    loader.parse(testdata.filepath('ofx', 'desjardins.ofx'))
    loader.load()
    return loader

def test_accounts_desjardins():
    loader = loader_desjardins()
    accounts = [(x.name, x.currency) for x in loader.accounts]
    expected = [('815-30219-12345-EOP', 'CAD'),
                ('815-30219-54321-ES1', 'CAD'),
                ('815-30219-11111-EOP', 'USD'),]
    eq_(accounts, expected)

def test_transactions_usd_account():
    loader = loader_desjardins()
    account = loader.accounts.find('815-30219-11111-EOP')
    entries = loader.accounts.entries_for_account(account)
    eq_(len(entries), 3)
    entries = list(entries)
    entry = entries[0]
    eq_(entry.date, date(2008, 1, 31))
    eq_(entry.description, 'Intérêt sur EOP/')
    eq_(entry.amount, Amount(0.02, 'USD'))
    entry = entries[1]
    eq_(entry.date, date(2008, 2, 1))
    eq_(entry.description, 'Dépôt au comptoir/')
    eq_(entry.amount, Amount(5029.50, 'USD'))
    entry = entries[2]
    eq_(entry.date, date(2008, 2, 1))
    eq_(entry.description, 'Retrait au comptoir/')
    eq_(entry.amount, Amount(-2665, 'USD'))

def test_reference_desjardins():
    # OFX IDs are stored in the accounts and entries.
    loader = loader_desjardins()
    account = list(loader.accounts)[0]
    eq_(account.reference, '700000100|0389347|815-30219-12345-EOP')
    transaction = list(loader.transactions)[0]
    eq_(transaction.splits[0].reference, 'Th3DJACES')

# ---
def loader_ing():
    loader = ofx.Loader('USD')
    loader.parse(testdata.filepath('ofx', 'ing.qfx'))
    loader.load()
    return loader

def test_accounts_ing():
    loader = loader_ing()
    accounts = [(x.name, x.currency) for x in loader.accounts]
    expected = [('123456', 'CAD')]
    eq_(accounts, expected)

def test_entries_ing():
    loader = loader_ing()
    account = loader.accounts.find('123456')
    entries = loader.accounts.entries_for_account(account)
    eq_(len(entries), 1)
    entry = next(iter(entries))
    eq_(entry.date, date(2005, 9, 23))
    eq_(entry.description, 'Dépôt')
    eq_(entry.amount, Amount(100, 'CAD'))

# ---
def loader_fortis():
    loader = ofx.Loader('EUR')
    loader.parse(testdata.filepath('ofx', 'fortis.ofx'))
    loader.load()
    return loader

def test_reference_fortis():
    # Fortis ofx files don't have a branch id. The reference should exist even without it.
    loader = loader_fortis()
    account = list(loader.accounts)[0]
    eq_(account.reference, 'FORTIS||001-5587496-84')
    transaction = list(loader.transactions)[0]
    eq_(transaction.splits[0].reference, '20080026')

# ---
def loader_ccstmtrs():
    loader = ofx.Loader('EUR')
    loader.parse(testdata.filepath('ofx', 'ccstmtrs.ofx'))
    loader.load()
    return loader

def test_ccstmtrs():
    # Sometimes, instead of STMTRS tags, we have CCSTMTRS tags and they need to be correctly
    # handled
    loader = loader_ccstmtrs()
    accounts = list(loader.accounts)
    eq_(len(accounts), 2)
    account = accounts[0]
    eq_(account.name, '4XXXXXXXXXXXXXX5')
    entries = loader.accounts.entries_for_account(account)
    eq_(len(entries), 2)
    account = accounts[1]
    eq_(account.name, '4XXXXXXXXXXXXXX9')
    entries = loader.accounts.entries_for_account(account)
    eq_(len(entries), 3)
