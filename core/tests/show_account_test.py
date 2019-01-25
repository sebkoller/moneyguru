# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

"""Tests on the topic of the "show account" feature.

These are tests for when we use the "Show Account" feature which has a different meaning depending
on the active view. See :meth:`MainWindow.show_account` for details.

This unit regroups tests for all active view scenarios.
"""

from .testutil import eq_

from ..const import PaneType, AccountType
from .base import TestApp, with_app

# ---
def test_show_transfer_account_on_empty_row_does_nothing():
    # show_transfer_account() when the table is empty doesn't do anything
    app = TestApp()
    app.add_account()
    app.show_account()
    app.etable.show_transfer_account() # no crash

def test_selection_is_kept_on_show_account():
    # Performing a show_account() keeps the txn selection in the newly shown account.
    app = TestApp()
    app.add_accounts('one', 'two', 'three') # three is the selected account (in second position)
    app.show_account()
    app.add_entry(description='foo', transfer='one')
    app.add_entry(description='bar', transfer='one')
    # first, let's open the accounts to make sure that selection restoration is not based on
    # simple initialization, but rather on the show_account() action
    aview_one = app.show_account('one')
    aview_three = app.show_account('three')
    assert app.current_view() is aview_three
    aview_three.etable.select([0])
    aview_one.etable.view.clear_gui_calls()
    aview_three.etable.show_transfer_account()
    assert app.current_view() is aview_one
    eq_(aview_one.etable.selected_indexes, [0])
    aview_one.etable.view.check_gui_calls_partial(['update_selection'])

def test_show_transfer_account_when_entry_has_no_transfer():
    # show_transfer_account() does nothing when an entry has no transfer
    app = TestApp()
    app.add_account('account')
    app.show_account()
    app.add_entry(description='foobar', decrease='130')
    app.etable.show_transfer_account() # no crash
    app.check_current_pane(PaneType.Account, account_name='account')

def test_show_from_account_when_theres_none_does_nothing():
    # show_from_account() when the selected txn has no assigned account does nothing
    app = TestApp()
    app.show_tview()
    app.clear_gui_calls()
    app.ttable.show_from_account() # no crash
    app.check_gui_calls_partial(app.mainwindow_gui, not_expected=['show_entry_table'])

def test_show_from_account():
    # show_from_account() takes the first account in the From column and shows it in etable.
    app = TestApp()
    app.drsel.select_month_range()
    app.add_account('first')
    app.add_txn(
        '11/07/2008', 'description', 'payee', from_='first', to='second', amount='42', checkno='24'
    )
    app.clear_gui_calls()
    app.ttable.show_from_account()
    app.check_current_pane(PaneType.Account, account_name='first')

def test_show_from_account_unassigned_txn():
    # show_from_account() when the selected txn has no assigned account does nothing
    app = TestApp()
    app.show_tview()
    app.ttable.add()
    app.ttable[0].amount = '42'
    app.ttable.save_edits()
    app.ttable.show_from_account() # no crash
    app.check_gui_calls_partial(app.mainwindow_gui, not_expected=['show_entry_table'])

def test_show_transfer_account_duplicate_splits():
    # When a split txn has the same account multiple times in its splits, this doesn't prevent the
    # account cycling from going through all accounts. Previously, we would get "stuck" at the
    # double account occurrence.
    app = TestApp()
    app.add_txn_with_splits(
        [
            ('a', '', '', '100'),
            ('b', '', '40', ''),
            ('b', '', '30', ''),
            ('c', '', '30', ''),
        ],
    ) # now in a tview
    app.mw.show_account()
    app.check_current_pane(PaneType.Account, account_name='a')
    app.mw.show_account()
    app.check_current_pane(PaneType.Account, account_name='b')
    app.mw.show_account() # doesn't get stuck on 'b'
    app.check_current_pane(PaneType.Account, account_name='c')

# ---
def app_one_entry():
    app = TestApp()
    app.drsel.select_month_range()
    app.add_account('first')
    app.show_account()
    app.add_entry('11/07/2008', 'description', 'payee', transfer='second', decrease='42')
    app.clear_gui_calls()
    return app

@with_app(app_one_entry)
def test_show_transfer_account_entry_with_transfer_selected(app):
    # show_transfer_account() changes the shown account to 'second'
    app.etable.show_transfer_account()
    app.link_aview()
    app.check_current_pane(PaneType.Account, account_name='second')
    # Previously, this was based on selected_account rather than shown_account
    assert not app.etable.columns.column_is_visible('balance')

@with_app(app_one_entry)
def test_show_transfer_account_then_add_entry(app):
    # When a new entry is created, it is created in the *shown* account, not the *selected*
    # account.
    app.etable.show_transfer_account()
    app.link_aview()
    app.mainwindow.new_item()
    app.etable.save_edits()
    eq_(app.etable_count(), 2)

@with_app(app_one_entry)
def test_show_transfer_account_twice(app):
    # calling show_transfer_account() again brings the account view on 'first'
    app.etable.show_transfer_account()
    app.link_aview()
    app.etable.show_transfer_account()
    app.check_current_pane(PaneType.Account, account_name='first')

# ---
def app_two_entries():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry('11/07/2008', 'first', transfer='account1', increase='42')
    app.add_entry('12/07/2008', 'second', transfer='account2', decrease='12')
    app.clear_gui_calls()
    return app

@with_app(app_two_entries)
def test_show_transfer_specify_index(app):
    # When a row index is specified in show_transfer(), we use this index instead of the selected
    # row. second row is selected now.
    app.etable.show_transfer_account(row_index=0)
    app.check_current_pane(PaneType.Account, account_name='account1')

@with_app(app_two_entries)
def test_show_transfer_specify_index_nothing_selected(app):
    # An empty selection doesn't prevent show_transfer_account from working with a specified row.
    app.etable.select([])
    app.etable.show_transfer_account(row_index=0)
    app.check_current_pane(PaneType.Account, account_name='account1')

# ---
def app_split_transaction():
    app = TestApp()
    app.add_account('first')
    app.show_account()
    app.add_entry('08/11/2008', description='foobar', transfer='second', increase='42')
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.add()
    stable.selected_row.account = 'third'
    stable.selected_row.debit = '20'
    stable.save_edits()
    tpanel.save()
    return app

def test_show_transfer_account():
    # show_transfer_account() cycles through all splits of the entry
    app = app_split_transaction()
    app.etable.show_transfer_account()
    app.link_aview()
    app.check_current_pane(PaneType.Account, account_name='second')
    app.etable.show_transfer_account()
    app.link_aview()
    app.check_current_pane(PaneType.Account, account_name='third')
    app.etable.show_transfer_account()
    app.link_aview()
    app.check_current_pane(PaneType.Account, account_name='first')

def test_show_transfer_account_with_unassigned_split():
    # If there's an unassigned split among the splits, just skip over it
    app = app_split_transaction()
    tpanel = app.mainwindow.edit_item()
    stable = tpanel.split_table
    stable.select([1]) # second
    stable.selected_row.account = ''
    stable.save_edits()
    tpanel.save()
    app.etable.show_transfer_account() # skip unassigned, and to to third
    app.check_current_pane(PaneType.Account, account_name='third')

# ---
def app_three_transactions():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry('11/07/2008', description='first', transfer='first', increase='1')
    app.add_entry('11/07/2008', description='second', transfer='second', increase='2')
    app.add_entry('12/07/2008', description='third', transfer='third', increase='3')
    app.show_tview()
    return app

@with_app(app_three_transactions)
def test_show_from_account_specify_index(app):
    # If a row index is supplied, use this row instead of the selected one.
    # The currently selected txn in the 3rd one.
    app.ttable.show_from_account(row_index=0)
    app.check_current_pane(PaneType.Account, account_name='first')

@with_app(app_three_transactions)
def test_show_from_account_specify_index_nothing_selected(app):
    # An empty selection doesn't prevent show_from_account from working with a specified row.
    app.ttable.select([])
    app.ttable.show_from_account(row_index=0)
    app.check_current_pane(PaneType.Account, account_name='first')

# ---
def app_account_hierarchy():
    app = TestApp()
    app.add_account('Asset 1', account_number='4242')
    app.add_group('Bank')
    app.add_account('Bank 1', group_name='Bank')
    app.add_account('Liability 1', account_type=AccountType.Liability)
    app.add_group('Loans', account_type=AccountType.Liability)
    app.add_account('Loan 1', account_type=AccountType.Liability, group_name='Loans')
    app.show_nwview()
    app.clear_gui_calls()
    return app

@with_app(app_account_hierarchy)
def test_show_selected_account(app):
    # show_selected_account() switches to the account view.
    app.bsheet.selected = app.bsheet.assets[0][0]
    app.clear_gui_calls()
    app.show_account()
    # no show_line_graph because it was already selected in the etable view before
    app.check_current_pane(PaneType.Account, account_name='Bank 1')

@with_app(app_account_hierarchy)
def test_show_account(app):
    # show_account() switches to the account view.
    app.bsheet.show_account([0, 0, 0])
    app.check_current_pane(PaneType.Account, account_name='Bank 1')

