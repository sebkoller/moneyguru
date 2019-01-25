# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..testutil import eq_

from ..base import TestApp, with_app
from ...const import AccountType
from ...model.currency import Currencies

# --- Some account
def app_some_account():
    app = TestApp()
    app.add_account('foobar', 'CAD', account_type=AccountType.Expense, account_number='4242')
    app.show_pview()
    return app

@with_app(app_some_account)
def test_change_currency_index(app):
    # Changing currency_index correctly updates the currency.
    apanel = app.mw.edit_item()
    apanel.currency_list.select(0)
    eq_(apanel.currency, Currencies.code_at_index(0))
    apanel.currency_list.select(42)
    eq_(apanel.currency, Currencies.code_at_index(42))

@with_app(app_some_account)
def test_change_type_index(app):
    # Changing type_index correctly updates the type.
    apanel = app.mw.edit_item()
    apanel.type_list.select(0)
    eq_(apanel.type, AccountType.Asset)
    apanel.type_list.select(1)
    eq_(apanel.type, AccountType.Liability)
    apanel.type_list.select(2)
    eq_(apanel.type, AccountType.Income)
    apanel.type_list.select(4) # Selects the highest index possible
    eq_(apanel.type, AccountType.Expense)
    eq_(apanel.type_list.selected_index, 3)

@with_app(app_some_account)
def test_fields(app):
    # The base field values.
    apanel = app.mw.edit_item()
    eq_(apanel.name, 'foobar')
    eq_(apanel.type, AccountType.Expense)
    eq_(apanel.currency, 'CAD')
    eq_(apanel.type_list.selected_index, 3) # Expense type is last in the list
    eq_(Currencies.code_at_index(apanel.currency_list.selected_index), 'CAD')
    eq_(apanel.account_number, '4242')
    assert not apanel.inactive
    eq_(apanel.notes, '')

@with_app(app_some_account)
def test_load_stops_edition(app):
    # edition must be stop on apanel load or else an account type change can result in a crash
    app.clear_gui_calls()
    app.mw.edit_item()
    app.check_gui_calls(app.istatement_gui, ['stop_editing'])

# --- Two accounts
def app_two_accounts():
    app = TestApp()
    app.add_account('foobar')
    app.add_account('foobaz')
    app.clear_gui_calls()
    return app

@with_app(app_two_accounts)
def test_duplicate_name(app):
    # setting a duplicate account name makes the dialog show a warning label
    apanel = app.mw.edit_item()
    apanel.name = 'foobar'
    apanel.save() # the exception doesn't propagate

@with_app(app_two_accounts)
def test_save_then_load(app):
    # save() calls document.change_account with the correct arguments and triggers a refresh on
    # all GUI components. We have to test this on two accounts to make sure that the values we test
    # on load aren't just leftovers from past assignments
    apanel = app.mw.edit_item() # foobaz
    apanel.type_list.select(1)
    apanel.currency_list.select(42)
    apanel.name = 'changed name'
    apanel.account_number = '4241'
    apanel.inactive = True
    apanel.notes = 'some notes'
    apanel.save()
    app.bsheet.selected = app.bsheet.assets[0] # foobar
    apanel = app.mw.edit_item()
    apanel.type_list.select(0)
    apanel.currency_list.select(0)
    apanel.name = 'whatever'
    apanel.account_number = '1234'
    apanel.notes = 'other notes'
    apanel.save()
    # To test the currency, we have to load again
    app.bsheet.selected = app.bsheet.liabilities[0] # foobaz
    apanel = app.mw.edit_item()
    eq_(apanel.currency, Currencies.code_at_index(42))
    eq_(apanel.type, AccountType.Liability)
    eq_(apanel.name, 'changed name')
    eq_(apanel.account_number, '4241')
    assert apanel.inactive
    eq_(apanel.notes, 'some notes')
