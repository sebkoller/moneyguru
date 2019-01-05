# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

import pytest

from ..testutil import eq_

from ...model.currency import Currencies
from ..base import TestApp, with_app

# --- Pristine
def test_can_load():
    # When there's no selection, we don't raise a panel
    app = TestApp()
    assert app.mw.edit_item() is None # no panel returned

# --- One Entry
def app_one_entry():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42')
    return app

def test_add_cancel_then_load():
    # when loading the tpanel right after cancelling a txn addition, the wrong txn is loaded
    app = app_one_entry()
    app.etable.add()
    app.etable.cancel_edits()
    tpanel = app.mw.edit_item()
    eq_(tpanel.description, 'description')

def test_buffer():
    # tpanel's edition is buffered.
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    tpanel.date = '07/07/2008'
    tpanel.description = 'foo'
    tpanel.payee = 'bar'
    tpanel.checkno = 'baz'
    tpanel = app.mw.edit_item()
    eq_(tpanel.date, '06/07/2008')
    eq_(tpanel.description, 'description')
    eq_(tpanel.payee, 'payee')
    eq_(tpanel.checkno, '42')

def test_can_load_selected_transaction():
    # Whether load() is possible is based on the last selection of either the etable or the ttable
    app = app_one_entry()
    app.etable.select([])
    app.show_tview()
    app.ttable.select([0])
    app.mw.edit_item() # no crash

def test_load_refreshes_mct_button():
    # loading the panel refreshes the mct button
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    tpanel.view.check_gui_calls_partial(['refresh_for_multi_currency'])

def test_load_while_etable_is_editing():
    # loading the tpanel while etable is editing aborts the edits and stops
    # editing mode.
    app = app_one_entry()
    app.etable.add()
    row = app.etable.edited
    row.date = '07/07/2008'
    app.clear_gui_calls()
    app.mw.edit_item()
    assert app.etable.edited is None
    eq_(app.etable_count(), 1)
    app.etable.view.check_gui_calls_partial(['stop_editing'])

def test_load_while_ttable_is_editing():
    # loading the tpanel while ttable is editing aborts the edits and stops
    # editing mode.
    app = app_one_entry()
    app.show_tview()
    app.ttable.add()
    row = app.ttable.edited
    row.date = '07/07/2008'
    app.clear_gui_calls()
    app.mw.edit_item()
    assert app.ttable.edited is None
    eq_(app.ttable.row_count, 1)
    app.ttable.view.check_gui_calls_partial(['stop_editing'])

def test_values():
    # The values of the panel are correct.
    app = app_one_entry()
    tpanel = app.mw.edit_item()
    eq_(tpanel.date, '06/07/2008')
    eq_(tpanel.description, 'description')
    eq_(tpanel.payee, 'payee')
    eq_(tpanel.checkno, '42')

def test_values_after_deselect():
    # When there is no selection, load() is not possible
    app = app_one_entry()
    app.etable.select([])
    assert app.mw.edit_item() is None # no panel returned

# --- Amountless Entry Panel Loaded
def app_amountless_entry_panel_loaded():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(date='06/07/2008', description='description', payee='payee', checkno='42')
    app.show_tview()
    app.ttable.select([0])
    app.mw.edit_item()
    app.clear_gui_calls()
    return app

# --- Entry With Amount Panel Loaded
def app_entry_with_amount_panel_loaded():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(date='06/07/2008', description='description', increase='42')
    app.show_tview()
    app.ttable.select([0])
    app.mw.edit_item()
    app.clear_gui_calls()
    return app

def test_change_date():
    # Changing the date no longer calls refresh_repeat_options() on the view (this stuff is now
    # in schedules)
    app = app_entry_with_amount_panel_loaded()
    tpanel = app.get_current_panel()
    tpanel.date = '17/07/2008'
    tpanel.view.check_gui_calls_partial(not_expected=['refresh_repeat_options'])

# --- Two Amountless Entries
def app_two_amountless_entries():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(date='06/07/2008', description='desc1', payee='payee1', checkno='42')
    app.add_entry(date='07/07/2008', description='desc2', payee='payee2', checkno='43')
    return app

def test_loads_last_selected_transaction():
    # the tpanel also works with the ttable. If the ttable is the last to have had a selection,
    # tpanel loads this one.
    app = app_two_amountless_entries()
    app.show_tview()
    app.ttable.select([0]) # etable has index 1 selected
    tpanel = app.mw.edit_item()
    eq_(tpanel.description, 'desc1')

@pytest.mark.parametrize(
    'attrname, newvalue, othervalue', [
        ('date', '08/07/2008', '06/07/2008'),
        ('description', 'new', 'desc1'),
        ('payee', 'new', 'payee1'),
        ('checkno', '44', '42'),
        ('notes', 'foo\nbar', ''),
    ])
def test_set_values(attrname, newvalue, othervalue):
    # the load/save mechanism works for all attributes.
    # The reason why we select another entry is to make sure that the value we're testing isn't
    # simply a buffer in the gui layer.
    app = app_two_amountless_entries()
    tpanel = app.mw.edit_item()
    setattr(tpanel, attrname, newvalue)
    tpanel.save()
    app.etable.select([0])
    tpanel = app.mw.edit_item()
    eq_(getattr(tpanel, attrname), othervalue)
    app.etable.select([1])
    tpanel = app.mw.edit_item()
    eq_(getattr(tpanel, attrname), newvalue)

# --- Multi-Currency Transaction
def app_multi_currency_transaction():
    app = TestApp()
    Currencies.get_rates_db().set_CAD_value(date(2008, 1, 1), 'USD', 0.8)
    splits = [
        ('first', '', '', '44 usd'),
        ('second', '', '42 cad', ''),
    ]
    app.add_txn_with_splits(splits)
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([1])
    app.clear_gui_calls()
    return app

def test_mct_balance():
    # a mct balance takes the "lowest side" of the transaction and adds a split with the
    # difference on that side. For this example, the usd side is the weakest side (if they were
    # equal, it would be 52.50 usd).
    app = app_multi_currency_transaction()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    tpanel.mct_balance()
    eq_(len(stable), 3)
    eq_(stable[2].credit, 'CAD 6.80') # the selected split is the 2nd one
    stable.view.check_gui_calls_partial(['refresh'])

@with_app(app_multi_currency_transaction)
def test_mct_balance_reuses_unassigned_split(app):
    # mct balance reuses unassigned split if available
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable.add()
    stable[2].credit = '1 cad'
    stable.save_edits()
    tpanel.mct_balance()
    eq_(len(stable), 3)
    eq_(stable[2].credit, 'CAD 6.80')

def test_mct_balance_select_null_split():
    # if the selected split has no amount, use the default currency
    app = app_multi_currency_transaction()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable.add()
    tpanel.mct_balance()
    eq_(stable[2].credit, '8.50') # the newly added split is re-used

def test_mct_balance_select_usd_split():
    # the currency of the new split is the currency of the selected split
    app = app_multi_currency_transaction()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable.select([0])
    tpanel.mct_balance()
    eq_(stable[2].credit, '8.50')

def test_mct_balance_twice():
    # if there is nothing to balance, don't add anything.
    app = app_multi_currency_transaction()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    tpanel.mct_balance()
    tpanel.mct_balance()
    eq_(len(stable), 3)

def test_stop_edition_on_mct_balance():
    # edition must stop before mct balance or else we end up with a crash
    app = app_multi_currency_transaction()
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable[1].account = 'foo'
    tpanel.mct_balance()
    stable.view.check_gui_calls_partial(['stop_editing'])

@with_app(app_multi_currency_transaction)
def test_mct_assign_imbalance_assigns_only_same_currency(app):
    # When doing Assign imbalance in an MCT context, assign only imbalance in the same currency
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable.add()
    stable[2].debit = '1 cad'
    stable.save_edits()
    stable.add()
    stable[3].credit = '2 usd'
    stable.save_edits()
    stable.select(0)
    tpanel.assign_imbalance() # no crash
    eq_(stable[0].credit, '46.00')

@with_app(app_multi_currency_transaction)
def test_mct_assign_imbalance_zero_amount_selected(app):
    # When doing Assign imbalance in an MCT context with a 0 amount selected, use whichever
    # unassigned split comes first as the base currency.
    tpanel = app.get_current_panel()
    stable = tpanel.split_table
    stable.add()
    stable[2].debit = '1 cad'
    stable.save_edits()
    stable.add()
    stable[3].credit = '2 usd'
    stable.save_edits()
    stable.add()
    stable[4].account = 'whatever'
    stable.save_edits()
    stable.select(4)
    tpanel.assign_imbalance() # no crash
    # CAD split is the first, and the split was deleted so our new index is 3
    eq_(len(stable), 4)
    eq_(stable[3].debit, 'CAD 1.00')

# --- Unassigned split
def app_with_unassigned_split():
    app = TestApp()
    splits = [
        ('account1', '', '42', ''),
        ('account2', '', '', '42'),
        ('account3', '', '15', ''),
    ]
    app.add_txn_with_splits(splits=splits, date='07/11/2014')
    return app

@with_app(app_with_unassigned_split)
def test_assign_imbalance_same_side(app):
    # When triggering Assign imbalance with a split on the "same side" as unassigned splits, we add
    # the value to it.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select(1)
    tpanel.assign_imbalance()
    eq_(stable[1].credit, '57.00')

@with_app(app_with_unassigned_split)
def test_assign_imbalance_other_side(app):
    # When triggering Assign imbalance with a split on the "other side" as unassigned splits, we subtract
    # the value to it.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select(0)
    tpanel.assign_imbalance()
    eq_(stable[0].debit, '27.00')

@with_app(app_with_unassigned_split)
def test_assign_imbalance_unassigned_selected(app):
    # When triggering Assign imbalance with an unassigned split, nothing happens.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select(3)
    tpanel.assign_imbalance()
    eq_(stable[3].credit, '15.00')

@with_app(app_with_unassigned_split)
def test_assign_imbalance_nothing_selected(app):
    # When triggering Assign imbalance with no selected split, nothing happens.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([])
    tpanel.assign_imbalance() # no crash
    eq_(stable[3].credit, '15.00')

@pytest.mark.parametrize(
    'setupfunc, expected', [
        # doesn't crash if there is no split with amounts
        (app_amountless_entry_panel_loaded, False),
        # the mct balance button is enabled if the txn is a MCT
        (app_entry_with_amount_panel_loaded, False),
        # the mct balance button is enabled if the txn is a MCT
        (app_multi_currency_transaction, True),
    ])
def test_is_multi_currency(setupfunc, expected):
    app = setupfunc()
    tpanel = app.mw.edit_item()
    eq_(tpanel.is_multi_currency, expected)

