# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..testutil import eq_

import pytest

from ...gui.mass_edition_panel import MassEditionPanel
from ..base import TestApp, with_app

# --- Two Transactions
def app_two_transactions():
    app = TestApp()
    app.show_tview()
    app.ttable.add()
    app.ttable.save_edits()
    app.ttable.add()
    app.ttable.save_edits()
    app.ttable.select([0, 1])
    return app

@with_app(app_two_transactions)
def test_can_load_after_selection(app):
    # When there is more than one txn selected, load() can be called
    # This test has a collateral, which is to make sure that mepanel doesn't have a problem
    # loading txns with splits with None accounts.
    assert isinstance(app.mw.edit_item(), MassEditionPanel)

@with_app(app_two_transactions)
def test_save_out_of_range_currency_index(app):
    # When the currency index is out of range, don't crash.
    # (On OS X, when typing a currency that doesn't exist in the box, the index ends up being an
    # out of range one)
    mepanel = app.mw.edit_item()
    mepanel.currency_list.select(999999)
    mepanel.save() # no crash

@with_app(app_two_transactions)
def test_saving_nothing_does_nothing(app):
    # Don't initiate a transaction change if nothing is changed in the panel.
    app.save_file()
    mepanel = app.mw.edit_item()
    mepanel.save()
    assert not app.doc.is_dirty()

# --- Two transactions different values
def app_two_transactions_different_value():
    app = TestApp()
    app.add_account('from1')
    app.show_account()
    app.add_entry(date='06/07/2008', description='description1', payee='payee1', checkno='42', transfer='to1', decrease='42')
    app.add_account('from2')
    app.show_account()
    app.add_entry(date='07/07/2008', description='description2', payee='payee2', checkno='43', transfer='to2', decrease='43')
    app.show_tview()
    app.ttable.select([0, 1])
    app.mw.edit_item()
    return app

def test_attributes(monkeypatch):
    # All fields are disabled and empty.
    monkeypatch.patch_today(2010, 2, 20)
    app = app_two_transactions_different_value()
    mepanel = app.get_current_panel()
    assert mepanel.can_change_accounts
    assert mepanel.can_change_amount
    assert not mepanel.date_enabled
    assert not mepanel.description_enabled
    assert not mepanel.payee_enabled
    assert not mepanel.checkno_enabled
    assert not mepanel.from_enabled
    assert not mepanel.to_enabled
    assert not mepanel.amount_enabled
    eq_(mepanel.date_field.text, '20/02/2010')
    eq_(mepanel.description_field.text, '')
    eq_(mepanel.payee_field.text, '')
    eq_(mepanel.checkno_field.text, '')
    eq_(mepanel.from_field.text, '')
    eq_(mepanel.to_field.text, '')
    eq_(mepanel.amount_field.text, '0.00')

def test_change_field():
    # Changing a field enables the associated checkbox
    app = app_two_transactions_different_value()
    mepanel = app.get_current_panel()
    mepanel.view.clear_calls()
    mepanel.date_field.text = '08/07/2008'
    assert mepanel.date_enabled
    # just make sure they are not changed all at once
    assert not mepanel.description_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.description_field.text = 'foobar'
    assert mepanel.description_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.payee_field.text = 'foobar'
    assert mepanel.payee_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.checkno_field.text = '44'
    assert mepanel.checkno_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.from_field.text = 'foobar'
    assert mepanel.from_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.to_field.text = 'foobar'
    assert mepanel.to_enabled
    mepanel.view.check_gui_calls(['refresh'])
    mepanel.amount_field.text = '44'
    assert mepanel.amount_enabled
    mepanel.view.check_gui_calls(['refresh'])

def test_change_field_to_none():
    # the mass panel considers replaces None values with ''.
    app = app_two_transactions_different_value()
    mepanel = app.get_current_panel()
    mepanel.description_field.text = None
    mepanel.payee_field.text = None
    mepanel.checkno_field.text = None
    mepanel.from_field.text = None
    mepanel.to_field.text = None
    mepanel.amount_field.text = None
    assert not mepanel.description_enabled
    assert not mepanel.payee_enabled
    assert not mepanel.checkno_enabled
    assert not mepanel.from_enabled
    assert not mepanel.to_enabled
    assert not mepanel.amount_enabled
    eq_(mepanel.description_field.text, '')
    eq_(mepanel.payee_field.text, '')
    eq_(mepanel.checkno_field.text, '')
    eq_(mepanel.from_field.text, '')
    eq_(mepanel.to_field.text, '')
    eq_(mepanel.amount_field.text, '0.00')

def test_change_and_save():
    # save() performs mass edits on selected transactions.
    app = app_two_transactions_different_value()
    app.save_file()
    mepanel = app.get_current_panel()
    mepanel.date_field.text = '08/07/2008'
    mepanel.description_field.text = 'description3'
    mepanel.payee_field.text = 'payee3'
    mepanel.checkno_field.text = '44'
    mepanel.from_field.text = 'from3'
    mepanel.to_field.text = 'to3'
    mepanel.amount_field.text = '44'
    mepanel.save()
    assert app.doc.is_dirty()
    for row in app.ttable.rows:
        eq_(row.date, '08/07/2008')
        eq_(row.description, 'description3')
        eq_(row.payee, 'payee3')
        eq_(row.checkno, '44')
        eq_(row.from_, 'from3')
        eq_(row.to, 'to3')
        eq_(row.amount, '44.00')

def test_change_date_only():
    # Only change checked fields.
    app = app_two_transactions_different_value()
    mepanel = app.get_current_panel()
    mepanel.date_field.text = '08/07/2008'
    mepanel.description_field.text = 'description3'
    mepanel.payee_field.text = 'payee3'
    mepanel.checkno_field.text = '44'
    mepanel.from_field.text = 'from3'
    mepanel.to_field.text = 'to3'
    mepanel.amount_field.text = '44'
    mepanel.description_enabled = False
    mepanel.payee_enabled = False
    mepanel.checkno_enabled = False
    mepanel.from_enabled = False
    mepanel.to_enabled = False
    mepanel.amount_enabled = False
    mepanel.save()
    row = app.ttable[0]
    eq_(row.date, '08/07/2008')
    eq_(row.description, 'description1')
    eq_(row.payee, 'payee1')
    eq_(row.checkno, '42')
    eq_(row.from_, 'from1')
    eq_(row.to, 'to1')
    eq_(row.amount, '42.00')

def test_change_description_only():
    # test_change_date_only is not enough for complete coverage.
    app = app_two_transactions_different_value()
    mepanel = app.get_current_panel()
    mepanel.date_field.text = '08/07/2008'
    mepanel.description_field.text = 'description3'
    mepanel.date_enabled = False
    mepanel.save()
    row = app.ttable[0]
    eq_(row.date, '06/07/2008')
    eq_(row.description, 'description3')

# --- Two transactions same values
def app_two_transactions_same_values():
    app = TestApp()
    app.add_account('account1')
    app.show_account()
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42', transfer='account2', increase='42')
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42', transfer='account2', increase='42')
    app.etable.select([0, 1])
    app.mw.edit_item()
    return app

@with_app(app_two_transactions_same_values)
def test_attributes_when_same_values(app):
    # All fields are disabled but contain the values common to all selection.
    mepanel = app.get_current_panel()
    assert not mepanel.date_enabled
    assert not mepanel.description_enabled
    assert not mepanel.payee_enabled
    assert not mepanel.checkno_enabled
    assert not mepanel.from_enabled
    assert not mepanel.to_enabled
    assert not mepanel.amount_enabled
    eq_(mepanel.date_field.text, '06/07/2008')
    eq_(mepanel.description_field.text, 'description')
    eq_(mepanel.payee_field.text, 'payee')
    eq_(mepanel.checkno_field.text, '42')
    eq_(mepanel.from_field.text, 'account2')
    eq_(mepanel.to_field.text, 'account1')
    eq_(mepanel.amount_field.text, '42.00')

@with_app(app_two_transactions_same_values)
def test_change_field_same(app):
    # Don't auto-enable when changing a field to the same value.
    mepanel = app.get_current_panel()
    mepanel.date = '06/07/2008'
    assert not mepanel.date_enabled
    mepanel.description = 'description'
    assert not mepanel.description_enabled
    mepanel.payee = 'payee'
    assert not mepanel.payee_enabled
    mepanel.checkno = '42'
    assert not mepanel.checkno_enabled
    mepanel.from_ = 'account2'
    assert not mepanel.from_enabled
    mepanel.to = 'account1'
    assert not mepanel.to_enabled
    mepanel.amount = '42'
    assert not mepanel.amount_enabled

@with_app(app_two_transactions_same_values)
def test_load_again(app, monkeypatch):
    # load() blanks values when necessary.
    monkeypatch.patch_today(2010, 2, 20)
    mepanel = app.get_current_panel()
    mepanel.date_enabled = True
    mepanel.description_enabled = True
    mepanel.payee_enabled = True
    mepanel.checkno_enabled = True
    mepanel.from_enabled = True
    mepanel.amount_enabled = True
    app.add_entry(date='07/07/2008') # Now, none of the values are common
    app.etable.select([0, 1, 2])
    mepanel = app.mw.edit_item()
    assert not mepanel.date_enabled
    assert not mepanel.description_enabled
    assert not mepanel.payee_enabled
    assert not mepanel.checkno_enabled
    assert not mepanel.from_enabled
    assert not mepanel.to_enabled
    assert not mepanel.amount_enabled
    eq_(mepanel.date_field.text, '20/02/2010')
    eq_(mepanel.description_field.text, '')
    eq_(mepanel.payee_field.text, '')
    eq_(mepanel.checkno_field.text, '')

# --- Two transactions one split
def app_two_transactions_one_split():
    app = TestApp()
    app.add_account('account1')
    app.show_account()
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42', transfer='account2', increase='42')
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42', transfer='account2', increase='42')
    tpanel = app.mw.edit_item()
    tpanel.split_table.add()
    row = tpanel.split_table.selected_row
    row.account = 'account3'
    row.debit = '24'
    tpanel.split_table.save_edits()
    tpanel.save()
    app.etable.select([0, 1])
    app.mw.edit_item()
    return app

def test_cant_change_accounts():
    app = app_two_transactions_one_split()
    mepanel = app.get_current_panel()
    assert not mepanel.can_change_accounts


# --- Two foreign transactions
def app_two_foreign_transactions():
    app = TestApp()
    app.add_account('account1')
    app.show_account()
    app.add_entry(increase='42 eur')
    app.add_entry(increase='42 eur')
    app.show_tview()
    app.ttable.select([0, 1])
    app.mw.edit_item()
    return app

def test_amount_has_correct_currency():
    #The amount is shown with a currency code and the selected currency is the correct one
    app = app_two_foreign_transactions()
    mepanel = app.get_current_panel()
    eq_(mepanel.amount_field.text, 'EUR 42.00')
    eq_(mepanel.currency_list.selected_index, 1) # EUR

def test_change_currency():
    # It's possible to mass edit currency
    app = app_two_foreign_transactions()
    mepanel = app.get_current_panel()
    mepanel.currency_list.select(3) # CAD
    assert mepanel.currency_enabled
    mepanel.currency_list.select(-1)
    assert not mepanel.currency_enabled
    mepanel.currency_list.select(3) # CAD
    assert mepanel.currency_enabled
    mepanel.save()
    eq_(app.ttable[0].amount, 'CAD 42.00')
    eq_(app.ttable[1].amount, 'CAD 42.00')

# --- Two transactions with a multi-currency one
def app_two_transactions_with_a_multi_currency_one():
    app = TestApp()
    app.add_txn('20/02/2010')
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[0].credit = '44 usd'
    stable.save_edits()
    stable.select([1])
    stable[1].debit = '42 cad'
    stable.save_edits()
    tpanel.save()
    app.add_txn('20/02/2010')
    app.ttable.select([0, 1])
    app.mw.edit_item()
    return app

# --- Transactions with splits
def app_transactions_with_splits():
    app = TestApp()
    app.add_txn()
    splits = [
        ('foo', '', '20', ''),
        ('bar', '', '', '10'),
        ('baz', '', '', '10'),
    ]
    app.add_txn_with_splits(splits)
    app.ttable.select([0, 1])
    app.mw.edit_item()
    return app

@with_app(app_transactions_with_splits)
def test_currency_change_on_splits(app):
    # currency mass change also work on split transactions. There would previously be a crash.
    mepanel = app.get_current_panel()
    mepanel.currency_list.select(2) # GBP
    mepanel.save() # no crash
    eq_(app.ttable[1].amount, 'GBP 20.00')

# ---
def app_transactions_with_different_currencies():
    app = TestApp()
    app.add_txn(amount='42 eur')
    app.add_txn(amount='42 cad')
    app.ttable.select([0, 1])
    return app

@with_app(app_transactions_with_different_currencies)
def test_set_currency_to_native_one_when_we_cant_choose_one_from_selection(app):
    # There was a bug previously where the panel's currency could stay at -1, causing the mass panel
    # to change all currencies to XPF (the last currency in the currency list).
    mepanel = app.mw.edit_item()
    eq_(mepanel.currency_list.selected_index, 0) # USD

# ---
@pytest.mark.parametrize(
    'appfunc, expected', [
        # Splits prevent the Amount field from being enabled
        (app_two_transactions_one_split, False),
        # If a MCT is selected, amount is not editable
        (app_two_transactions_with_a_multi_currency_one, False),
    ])
def test_can_change_amount(appfunc, expected):
    app = appfunc()
    mepanel = app.get_current_panel()
    eq_(mepanel.can_change_amount, expected)
