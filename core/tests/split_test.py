# Created By: Virgil Dupras
# Created On: 2008-06-13
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .testutil import eq_

from .base import TestApp, with_app

def first_debit_credit_indexes(stable):
    return (0, 1) if stable[0].debit else (1, 0)

# --- Empty account
def app_empty_account():
    app = TestApp()
    app.add_account('Checking')
    app.show_account()
    return app

@with_app(app_empty_account)
def test_add_entry_check_splits(app):
    # A newly added entry has its splits set.
    # Previously, split_count() would be zero until a save_entry()
    app.etable.add()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(len(stable), 2)
    eq_(stable[0].account, 'Checking')
    eq_(stable[0].debit, '')
    eq_(stable[0].credit, '')
    eq_(stable[1].account, '')
    eq_(stable[1].debit, '')
    eq_(stable[1].credit, '')

@with_app(app_empty_account)
def test_add_entry_save_split(app):
    # Saving a split in a newly added entry doesn't make it disappear.
    # Previously, saving splits to a newly created entry would make it disappear because the
    # cooking would be made before the transaction could be added
    app.etable.add()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.add()
    stable.save_edits()
    tpanel.save()
    eq_(app.etable_count(), 1)

# --- One entry
def app_one_entry():
    app = TestApp()
    app.add_account('Checking')
    app.show_account()
    app.add_entry('10/10/2007', 'Deposit', transfer='Salary', increase='42.00')
    return app

@with_app(app_one_entry)
def test_reverse_main_split(app):
    # Reversing (changing it from debit to credit or vice versa) a main split reverses the other
    # main split.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    dindex, cindex = first_debit_credit_indexes(stable)
    stable[cindex].debit = '42'
    stable.save_edits()
    eq_(len(stable), 2)
    eq_(stable[cindex].debit, '42.00')
    eq_(stable[dindex].credit, '42.00')

@with_app(app_one_entry)
def test_save_split_on_second_row(app):
    # save_split() doesn't change the selected row.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([1])
    row = stable.selected_row
    row.account = 'foobar'
    stable.save_edits()
    eq_(stable.selected_index, 1)

@with_app(app_one_entry)
def test_split_are_correctly_assigned(app):
    # There are two splits and the attributes are correct.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(len(stable), 2)
    eq_(stable[0].account, 'Checking')
    eq_(stable[0].debit, '42.00')
    eq_(stable[1].account, 'Salary')
    eq_(stable[1].credit, '42.00')

@with_app(app_one_entry)
def test_set_split_credit(app):
    # Setting the split credit changes the split credit, the entry amount and the balance.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.credit = '100.00'
    stable.save_edits()
    tpanel.save()
    eq_(stable[0].credit, '100.00')
    eq_(app.etable[0].decrease, '100.00')
    eq_(app.etable[0].balance, '-100.00')

@with_app(app_one_entry)
def test_set_split_debit(app):
    # Setting the split debit changes the split debit, the entry amount and the balance.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.debit = '100.00'
    stable.save_edits()
    tpanel.save()
    eq_(stable[0].debit, '100.00')
    eq_(app.etable[0].increase, '100.00')
    eq_(app.etable[0].balance, '100.00')

@with_app(app_one_entry)
def test_set_split_account(app):
    # Setting the split account changes both the split and the entry. If the current entry's account
    # is changed, the account selection changes too.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.account = 'foo'
    stable.save_edits()
    tpanel.save()
    app.show_nwview()
    eq_(app.bsheet.assets[1].name, 'foo') # The foo account was autocreated
    app.bsheet.selected = app.bsheet.assets[1]
    app.show_account()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([1])
    row = stable.selected_row
    row.account = 'bar'
    stable.save_edits()
    tpanel.save()
    eq_(stable[1].account, 'bar')
    eq_(app.etable[0].transfer, 'bar')
    app.show_pview()
    eq_(app.istatement.income[0].name, 'bar') # The bar account was autocreated

@with_app(app_one_entry)
def test_divide_split_amount_rounding(app):
    # When setting an amount with an expression that results in amounts that are over the currency's
    # exponent, make sure that we don't end up with rounding errors.
    # First, let's change the entry's main amount so that we have two 12.37 splits.
    app.etable[0].increase = '12.37'
    app.etable.save_edits()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    dindex, cindex = first_debit_credit_indexes(stable)
    stable.select([dindex])
    stable[dindex].debit = '12.37/2'
    stable.save_edits()
    # This creates a 3rd split with the balance. Then, we test that we don't end up with two 6.18
    # splits! We test things so that we don't care which is 6.19 and which is 6.18 because wouldn't
    # want a specific python implementation to come and create a false failure.
    assert {stable[dindex].debit, stable[2].debit} == {'6.18', '6.19'}

# --- Entry without transfer
def app_entry_without_transfer():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(description='foobar', decrease='130.00')
    return app

@with_app(app_entry_without_transfer)
def test_split_has_unassigned_account(app):
    # There are two splits and their amounts and accounts are correct.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(len(stable), 2)
    eq_(stable[0].account, 'New account')
    eq_(stable[0].credit, '130.00')
    eq_(stable[1].account, '')
    eq_(stable[1].debit, '130.00')

# --- Split transaction
def app_split_transaction():
    # New Account   0 100
    # expense1    100   0
    # expense2     10   0
    # income        0   1
    # Unassigned    0   9
    app = TestApp()
    app.add_account('New Account')
    splits = [
        ('New Account', '', '', '100'),
        ('expense1', '', '100', ''),
        ('expense2', '', '10', ''),
        ('income', '', '', '1'),
    ] # there will be an unassigned for 9
    app.add_txn_with_splits(splits, date='2/1/2007', description='Split')
    app.show_account('New Account')
    app.add_entry(date='3/1/2007')   # That's to make sure the selection doesn't change on edits
    app.etable.select([0])
    return app

@with_app(app_split_transaction)
def test_amounts(app):
    # All split amounts are right.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(stable[0].credit, '100.00')
    eq_(stable[1].debit, '100.00')
    eq_(stable[2].debit, '10.00')
    eq_(stable[3].credit, '1.00')
    eq_(stable[4].credit, '9.00')
    eq_(app.etable[0].decrease, '100.00')

@with_app(app_split_transaction)
def test_delete_split(app):
    # Deleting a split works.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([2])
    stable.delete()
    eq_(len(stable), 4)
    # The unassigned split took the difference
    eq_(stable[2].account, 'income')
    eq_(stable[2].credit, '1.00')
    eq_(stable[3].debit, '1.00')

@with_app(app_split_transaction)
def test_neutralizing_unassigned_split_removes_it(app):
    # When editing a split results in an unassigned split being put to 0, we remove it.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[3].credit = '10' # The unsassigned split should end up being deleted.
    stable.save_edits()
    eq_(len(stable), 4)

@with_app(app_split_transaction)
def test_revert_split(app):
    # Reverting the edits works.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    row = stable.selected_row
    row.account = 'changed'
    row.debit = '2'
    stable.cancel_edits()
    eq_(stable[3].account, 'income')
    eq_(stable[3].credit, '1.00')

@with_app(app_split_transaction)
def test_save_entry(app):
    # Saving an entry doesn't change the amounts.
    row = app.etable.selected_row
    row.description = 'Another description'
    app.etable.save_edits()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(len(stable), 5)
    eq_(stable[0].credit, '100.00')
    eq_(stable[1].debit, '100.00')
    eq_(stable[2].debit, '10.00')
    eq_(stable[3].credit, '1.00')
    eq_(stable[4].credit, '9.00')

@with_app(app_split_transaction)
def test_select_another_entry(app):
    # Selecting another entry resets the split index to 0.
    app.etable.select([1])
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(stable.selected_index, 0)

@with_app(app_split_transaction)
def test_split_count(app):
    # All splits are shown.
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    eq_(len(stable), 5)

@with_app(app_split_transaction)
def test_transfer_read_only(app):
    # The transfer column shows a list of affecter *other* accounts and is read-only.
    eq_(app.etable[0].transfer, 'expense1, expense2, income')
    assert not app.etable.can_edit_cell('transfer', 0)

# --- Split with no account
def app_split_with_no_account():
    app = TestApp()
    app.add_account()
    app.show_account()
    app.add_entry(date='2/1/2007', description='Split', transfer='expense1', decrease='100')
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.add()
    row = stable.selected_row
    row.credit = '10'
    stable.save_edits()
    tpanel.save()
    return app

@with_app(app_split_with_no_account)
def test_transfer_doesnt_include_unassigned_split(app):
    # The transfer column don't include splits with no account.
    eq_(app.etable[0].transfer, 'expense1')

# --- Split txn no unassigned
def app_split_txn_no_unassigned():
    app = TestApp()
    splits = [('foo', '', '37', ''), ('bar', '', '', '42'), ('baz', '', '5', '')]
    app.add_txn_with_splits(splits, date='20/02/2010')
    return app

def test_change_split_create_new_unassigned():
    # Changing a split creates a new unassigned split.
    app = app_split_txn_no_unassigned()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable[1].credit = '43'
    stable.save_edits()
    eq_(len(stable), 4)
    eq_(stable[3].account, '')
    eq_(stable[3].debit, '1.00')

def test_delete_split_creates_new_unassigned():
    # Deleting a split doesn't affect the txn amount. It recreates an unassigned split at stable's
    # bottom.
    app = app_split_txn_no_unassigned()
    tpanel = app.mw.edit_item()
    stable = tpanel.split_table
    stable.select([1])
    stable.delete()
    eq_(stable[1].debit, '5.00')
    eq_(stable[2].credit, '42.00')

