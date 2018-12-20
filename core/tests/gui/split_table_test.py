# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..testutil import eq_

from ..base import TestApp, with_app

# --- One entry
def app_one_entry():
    app = TestApp()
    app.add_account('first', currency='CAD')
    app.show_account()
    app.add_entry(transfer='second', increase='42')
    return app

def test_add_gui_calls():
    # refresh() and start_editing() are called after a add()
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.view.clear_calls()
    stable.add()
    stable.view.check_gui_calls(['refresh', 'start_editing', 'stop_editing'])

def test_cancel_edits():
    # cancel_edits() sets edited to None and makes the right gui calls
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[0].account = 'foo'
    stable.view.clear_calls()
    stable.cancel_edits()
    assert stable.edited is None
    stable.view.check_gui_calls(['refresh', 'stop_editing'])

@with_app(app_one_entry)
def test_cancel_edits_while_adding(app):
    # cancel_edits() removes edited row if it was being added
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.add()
    stable[2].account = 'foo'
    stable.cancel_edits()
    eq_(len(stable), 2)

def test_changes_split_buffer_only():
    # Changes made to the split table don't directly get to the model until tpanel.save().
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.debit = '40'
    stable.save_edits()
    # Now, let's force a refresh of etable
    app.show_nwview()
    app.bsheet.selected = app.bsheet.assets[0]
    app.show_account()
    eq_(app.etable[0].increase, 'CAD 42.00')

def test_completion():
    # Just make sure it works. That is enough to know SplitTable is of the right subclass.
    app = app_one_entry()
    ce = app.completable_edit('account')
    ce.text = 's'
    eq_(ce.completion, 'econd')

def test_completion_new_txn():
    # When completing an account from a new txn, the completion wouldn't work at all
    app = app_one_entry()
    app.show_tview()
    app.ttable.add()
    app.mw.edit_item()
    ce = app.completable_edit('account')
    ce.text = 'f'
    eq_(ce.completion, 'irst')

def test_load_tpanel_from_ttable():
    # When the tpanel is loaded form the ttable, the system currency is used.
    app = app_one_entry()
    app.show_tview()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(stable[0].debit, 'CAD 42.00')

def test_memo():
    # It's possible to set a different memo for each split.
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.memo = 'memo1'
    stable.save_edits()
    stable.select([1])
    row = stable.selected_row
    row.memo = 'memo2'
    stable.save_edits()
    tpanel.save()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(stable[0].memo, 'memo1')
    eq_(stable[1].memo, 'memo2')

def test_set_wrong_values_for_attributes():
    # set_attribute_value catches ValueError.
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.debit = 'invalid'
    row.credit = 'invalid'
    # no crash occured

# --- Transaction being added
def app_transaction_being_added():
    app = TestApp()
    app.show_tview()
    app.ttable.add()
    return app

@with_app(app_transaction_being_added)
def test_change_splits(app):
    # It's possible to change the splits of a newly created transaction.
    # Previously, it would crash because of the 0 amounts.
    # At this moment, we have a transaction with 2 empty splits
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[0].account = 'first'
    stable[0].credit = '42'
    stable.save_edits()
    stable.select([1])
    stable[1].account = 'second'
    stable.save_edits()
    tpanel.save()
    row = app.ttable[0]
    eq_(row.from_, 'first')
    eq_(row.to, 'second')
    eq_(row.amount, '42.00')

@with_app(app_transaction_being_added)
def test_delete_split_with_none_selected(app):
    # don't crash when stable.delete() is called enough times to leave the table empty
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.delete() # Unassigned 1
    stable.delete() # Unassigned 2
    try:
        stable.delete()
    except AttributeError:
        raise AssertionError("When the table is empty, don't try to delete")

# --- Transaction with splits
def app_transaction_with_splits():
    app = TestApp()
    app.add_txn(from_='foo', to='bar', amount='42')
    tpanel = app.mainwindow.edit_item()
    stable = tpanel.split_table
    stable.add()
    stable[2].account = 'baz'
    stable[2].credit = '3'
    stable.save_edits()
    return app

def test_auto_decimal_place():
    # the auto decimal place options affects the split table.
    app = app_transaction_with_splits()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    app.app.auto_decimal_place = True
    stable[0].debit = '1234'
    eq_(stable[0].debit, '12.34')

def test_move_split():
    # It's possible to move splits around
    app = app_transaction_with_splits()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    # order of first 2 splits is not defined
    first_account = stable[0].account
    second_account = stable[1].account
    stable.move_split(1, 0)
    eq_(stable[0].account, second_account)
    eq_(stable.selected_indexes, [0])
    stable.move_split(1, 2)
    eq_(stable[2].account, first_account)
    eq_(stable.selected_indexes, [2])

# --- EUR account and EUR transfer
def app_eur_account_and_eur_transfer():
    app = TestApp()
    app.add_account('first', 'EUR')
    app.add_account('second', 'EUR')
    app.show_account()
    app.add_entry(transfer='first', increase='42') # EUR
    return app

def test_amounts_display():
    # The amounts' currency are explicitly displayed.
    app = app_eur_account_and_eur_transfer()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(stable[0].debit, 'EUR 42.00')
    eq_(stable[1].credit, 'EUR 42.00')

def test_change_amount_implicit_currency():
    # When typing a currency-less amount, the transaction amount's currency is used.
    app = app_eur_account_and_eur_transfer()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[0].debit = '64'
    eq_(stable[0].debit, 'EUR 64.00')

