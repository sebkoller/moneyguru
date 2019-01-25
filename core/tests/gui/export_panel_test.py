# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import csv

from ..testutil import eq_

from ...gui.export_panel import ExportFormat
from ...const import AccountType
from ..base import TestApp, with_app

# ---
@with_app(TestApp)
def test_account_table_order(app):
    app.add_account('d', account_type=AccountType.Asset)
    app.add_account('c', account_type=AccountType.Liability)
    app.add_account('b', account_type=AccountType.Income) # not shown
    app.add_account('a', account_type=AccountType.Expense) # not shown
    app.mw.export()
    expanel = app.get_current_panel()
    t = expanel.account_table
    eq_(len(t), 2)
    eq_(t[0].name, 'd')
    eq_(t[1].name, 'c')

@with_app(TestApp)
def test_default_values(app):
    app.add_account('foo')
    app.mw.export()
    expanel = app.get_current_panel()
    assert expanel.export_all
    assert not expanel.account_table[0].export
    assert expanel.export_path is None

@with_app(TestApp)
def test_export_only_one_account(app):
    app.add_accounts('foobar', 'foobaz')
    app.mw.export()
    expanel = app.get_current_panel()
    expanel.export_all = False
    expanel.account_table[0].export = True
    expath = str(app.tmppath() + 'foo.qif')
    expanel.export_path = expath
    expanel.save()
    contents = open(expath, 'rt', encoding='utf-8').read()
    assert 'foobaz' not in contents

@with_app(TestApp)
def test_export_as_csv(app):
    app.add_account('foo')
    app.add_txn(to='foo', amount='42')
    app.mw.export()
    expanel = app.get_current_panel()
    expanel.export_format = ExportFormat.CSV
    expath = str(app.tmppath() + 'foo.csv')
    expanel.export_path = expath
    expanel.save()
    # We just check that the resulting file is a CSV. whether it's a correct CSV file is tested
    # elsewhere.
    contents = open(expath, 'rt').read()
    csv.Sniffer().sniff(contents) # no error? alright, it's a csv
