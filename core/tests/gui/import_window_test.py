# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date
from collections import defaultdict

from hscommon.testutil import eq_

from ..base import TestApp, with_app, DictLoader, testdata
from ...model.date import YearRange
from ...gui.import_window import ActionSelectionOptions

from core.model.transaction import Split
from core.model.account import AccountType
from core.model.amount import Amount
from core.plugin import ImportActionPlugin, ImportBindPlugin, EntryMatch

# Legacy structure
# This used to list the possible swap operations. Since the introduction of import plugins, this
# structure no longer makes sense. Because old tests are built around it, we keep it around, but
# only here.
class SwapType:
    DayMonth = 0
    MonthYear = 1
    DayYear = 2
    DescriptionPayee = 3
    InvertAmount = 4


# --- Support test plugin

class ChangeStructure(ImportActionPlugin):
    NAME = "Structure Change Import Plugin"
    ACTION_NAME = "Structure change import"

    def perform_action(self, import_document, transactions, panes, selected_rows=None):

        imbalance_account = import_document.accounts.find('imbalance account', AccountType.Expense)

        for transaction in transactions:
            if len(transaction.splits) == 2:
                # Wow, this was actually something pretty hard to do...
                txn_copy = transaction.replicate()
                if txn_copy.splits[0].amount == 0:  # If an amount is zero, it's an int...
                    amount_value = 0
                    amount_currency = import_document.default_currency
                else:
                    amount_value = float(txn_copy.splits[0].amount)
                    amount_currency = txn_copy.splits[0].amount.currency_code
                first_split_new_amount = Amount(amount_value+1, amount_currency)
                new_split_amount = Amount(-1.0, amount_currency)
                txn_copy.splits[0].amount = first_split_new_amount
                txn_copy.splits.append(Split(imbalance_account, new_split_amount))
                import_document.change_transaction(transaction, txn_copy)

class ChangeTransfer(ImportActionPlugin):
    """
    The point of this plugin is to change any transfer with the
    phrase 'automatic' to a checking account.
    """

    def always_perform_action(self):
        return True

    def perform_action(self, import_document, transactions, panes):
        auto_pays = []

        # We go through all of our transactions searching for the keyword
        # automatic.
        for txn in transactions:
            for split in txn.splits:
                if 'automatic' in split.account_name.lower():
                    # We collect up the actual account names marked for transfer
                    auto_pays.append(split.account_name)

        if not auto_pays:
            return

        checking = import_document.accounts.find('checking', AccountType.Asset)

        # Reassign our transfers to checking
        auto_pay_accounts = [import_document.accounts.find(ap) for ap in auto_pays]
        for account in auto_pay_accounts:
            import_document.transactions.reassign_account(account, checking)

class ValueImportBind(ImportBindPlugin):
    """A simple import binder that checks date + description + payee

    Match score increases with the number of fields that are the same
    """
    NAME = "Value Import Bind"

    def match_entries(self, target_account, document, import_document, existing_entries, imported_entries):
        matches = []
        import_date2entry = defaultdict(set)
        for e in imported_entries:
            import_date2entry[e.date].add(e)
        for existing_entry in existing_entries:
            if existing_entry.date not in import_date2entry:
                continue
            matching = import_date2entry[existing_entry.date]
            for import_entry in matching:
                score = 0.3
                if import_entry.description == existing_entry.description:
                    score += 0.3
                if import_entry.payee == existing_entry.payee:
                    score += 0.3
                matches.append(EntryMatch(existing_entry, import_entry, True, score))

        return matches

# --- No setup

@with_app(TestApp)
def test_MMM_date_formats_are_supported(app):
    TXNS = [
        {'date': '16 SEP 2012', 'amount': '1'},
    ]
    app.fake_import('foo', TXNS)
    app.iwin.import_selected_pane()
    eq_(app.itable[0].date_import, '16/09/2012')
    eq_(app.iwin.swap_type_list[0], "dd MMM yyyy --> MMM dd yyyy")

@with_app(TestApp)
def test_fuzzy_matching_plugin(app):
    # Verify that fuzzily matching entries on import can actually ever work (core plugins don't do
    # that (yet) so that's why we can only verify this with a dummy plugin).
    # Here, our higest score (date+desc+payee are matched, the last entry) is bound to our existing
    # entry. The rest is unbound.
    app.set_plugins([ValueImportBind])
    TXNS = [
        {'date': '22/06/2015', 'description': 'foo', 'payee': 'foo', 'amount': '1'},
    ]
    app.fake_import('foo', TXNS, account_reference='foo')
    app.iwin.import_selected_pane()
    TXNS = [
        {'date': '22/06/2015', 'description': 'bar', 'payee': 'bar', 'amount': '2'}, # date matching
        {'date': '22/06/2015', 'description': 'foo', 'payee': 'bar', 'amount': '3'}, # date+desc matching
        {'date': '22/06/2015', 'description': 'foo', 'payee': 'foo', 'amount': '4'}, # date+desc+payee matching
    ]
    app.fake_import('foo', TXNS, account_reference='foo')
    EXPECTED = [
        ('1.00', '4.00'),
        ('', '2.00'),
        ('', '3.00'),

    ]
    eq_(len(app.itable), len(EXPECTED))
    for row, (amount, amount_import) in zip(app.itable, EXPECTED):
        eq_(row.amount, amount)
        eq_(row.amount_import, amount_import)


# ---
def app_import_checkbook_qif():
    app = TestApp()
    app.clear_gui_calls()
    app.doc.date_range = YearRange(date(2007, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/checkbook.qif'))
    app.check_gui_calls(app.iwin.view, ['refresh_tabs', 'refresh_target_accounts', 'show'])
    return app

@with_app(app_import_checkbook_qif)
def test_account_tabs(app):
    # There is one account tab for each imported account, the first is selected, and each tab
    # has a counter indicating the number of entries in each account.
    eq_(len(app.iwin.panes), 2)
    eq_(app.iwin.panes[0].name, 'Account 1')
    eq_(app.iwin.panes[1].name, 'Account 2')
    eq_(app.iwin.panes[0].count, 5)
    eq_(app.iwin.panes[1].count, 3)
    eq_(app.iwin.selected_pane_index, 0)

@with_app(app_import_checkbook_qif)
def test_close_pane(app):
    # It's possible to close any pane
    app.iwin.close_pane(1) # It's not the selected pane
    eq_(len(app.iwin.panes), 1)
    eq_(app.iwin.panes[0].name, 'Account 1')
    eq_(app.iwin.panes[0].count, 5)

@with_app(app_import_checkbook_qif)
def test_close_selected_pane(app):
    # When closing the selected pane, everything is correctly refreshed
    app.add_account('bar')
    app.iwin.selected_target_account_index = 1
    app.iwin.close_pane(0)
    eq_(len(app.iwin.panes), 1)
    eq_(app.iwin.panes[0].name, 'Account 2')
    eq_(app.iwin.panes[0].count, 3)
    eq_(len(app.itable), 3)

@with_app(app_import_checkbook_qif)
def test_close_first_pane_when_selected_is_last(app):
    # When the selected pane index is last, closing it decrements the selected pane index
    app.iwin.selected_pane_index = 1
    app.iwin.close_pane(0)
    eq_(app.iwin.selected_pane_index, 0)

@with_app(app_import_checkbook_qif)
def test_close_selected_pane_when_last(app):
    # When the selected pane index is last, closing it decrements the selected pane index
    app.iwin.selected_pane_index = 1
    app.iwin.close_pane(1)
    eq_(app.iwin.selected_pane_index, 0)

@with_app(app_import_checkbook_qif)
def test_dirty(app):
    # Simply loading a file for import doesn't make the document dirty
    assert not app.doc.is_dirty()

@with_app(app_import_checkbook_qif)
def test_import_selected_pane(app):
    # import_selected_pane() imports the currenctly selected pane and closes it
    app.iwin.import_selected_pane()
    # The pane has been closed
    eq_(len(app.iwin.panes), 1)
    eq_(app.iwin.panes[0].name, 'Account 2')
    app.check_gui_calls(app.iwin.view, ['update_selected_pane', 'close_selected_tab', 'set_swap_button_enabled'])
    app.show_nwview()
    # The account & entries has been added
    eq_(app.bsheet.assets[0].name, 'Account 1')
    app.bsheet.selected = app.bsheet.assets[0]
    app.show_account()
    eq_(app.etable_count(), 5)
    # When importing the last pane, the window should close
    app.clear_gui_calls()
    app.iwin.import_selected_pane()
    app.check_gui_calls(app.iwin.view, ['close_selected_tab', 'close'])

@with_app(app_import_checkbook_qif)
def test_import_selected_pane_with_some_entries_disabled(app):
    # When the will_import checkbox is unchecked, don't import the entry
    app.itable[0].will_import = False
    app.iwin.import_selected_pane()
    app.show_nwview()
    app.bsheet.selected = app.bsheet.assets[0]
    app.show_account()
    eq_(app.etable_count(), 4)

@with_app(app_import_checkbook_qif)
def test_invert_amounts(app):
    app.iwin.swap_type_list.select(SwapType.InvertAmount)
    app.iwin.perform_swap()
    eq_(app.itable[0].amount_import, '-42.32')
    eq_(app.itable[1].amount_import, '-100.00')
    eq_(app.itable[2].amount_import, '60.00')

@with_app(app_import_checkbook_qif)
def test_remember_target_account_selection(app):
    # When selecting a target account, it's specific to the ane we're in
    app.add_account('foo')
    app.iwin.selected_target_account_index = 1
    app.clear_gui_calls()
    app.iwin.selected_pane_index = 1
    app.check_gui_calls(app.iwin.view, ['update_selected_pane', 'set_swap_button_enabled'])
    eq_(app.iwin.selected_target_account_index, 0)
    app.iwin.selected_target_account_index = 1
    app.iwin.selected_pane_index = 0
    eq_(app.iwin.selected_target_account_index, 1)
    # target account selection is instance based, not index based
    app.add_account('bar')
    eq_(app.iwin.selected_target_account_index, 2)
    app.iwin.selected_pane_index = 1
    eq_(app.iwin.selected_target_account_index, 2)

@with_app(app_import_checkbook_qif)
def test_select_out_of_range_tab_index(app):
    # ignore index set that are out of range
    app.iwin.selected_pane_index = 2
    eq_(app.iwin.selected_pane_index, 0)

@with_app(app_import_checkbook_qif)
def test_switch_description_payee(app):
    app.iwin.swap_type_list.select(SwapType.DescriptionPayee)
    app.iwin.perform_swap()
    # the 4th entry is the Hydro Quebec entry
    eq_(app.itable[3].description_import, 'Hydro-Quebec')
    eq_(app.itable[3].payee_import, 'Power Bill')

@with_app(app_import_checkbook_qif)
def test_target_accounts(app):
    # Target accounts are updated when accounts are added/removed
    eq_(app.iwin.target_account_names, ['< New Account >'])
    app.add_account('Foo')
    app.check_gui_calls(app.iwin.view, ['refresh_target_accounts'])
    app.add_account('bar')
    app.check_gui_calls(app.iwin.view, ['refresh_target_accounts'])
    eq_(app.iwin.target_account_names, ['< New Account >', 'bar', 'Foo'])
    app.show_nwview()
    app.bsheet.selected = app.bsheet.assets[0] # bar
    app.bsheet.delete()
    app.check_gui_calls(app.iwin.view, ['refresh_target_accounts'])
    eq_(app.iwin.target_account_names, ['< New Account >', 'Foo'])
    app.add_account()
    app.check_gui_calls(app.iwin.view, ['refresh_target_accounts'])
    eq_(app.iwin.target_account_names, ['< New Account >', 'Foo', 'New account'])

@with_app(app_import_checkbook_qif)
def test_swap_date_texts(app):
    # The first three items in the swap type list are date swapping actions and their text are in
    # the format <current date format> --> <format after swapping>.
    # checkbook.qif dates have the format MM/dd/yy
    eq_(app.iwin.swap_type_list[0], "MM/dd/yy --> dd/MM/yy")
    eq_(app.iwin.swap_type_list[1], "MM/dd/yy --> yy/dd/MM")
    eq_(app.iwin.swap_type_list[2], "MM/dd/yy --> MM/yy/dd")
    eq_(len(app.iwin.swap_type_list), 5) # the 3 date swaps + description swap + amount invert

@with_app(app_import_checkbook_qif)
def test_swap_date_texts_after_swap(app):
    # After a swap, the old date format becomes the new base date format, but only in the affected
    # pane.
    app.iwin.perform_swap() # Swap Day <--> Month
    eq_(app.iwin.swap_type_list[0], "dd/MM/yy --> MM/dd/yy")
    eq_(app.iwin.swap_type_list[1], "dd/MM/yy --> dd/yy/MM")
    eq_(app.iwin.swap_type_list[2], "dd/MM/yy --> yy/MM/dd")
    # ... but only the selected pane
    app.iwin.selected_pane_index = 1
    eq_(app.iwin.swap_type_list[0], "MM/dd/yy --> dd/MM/yy")

# ---
def app_import_checkbook_qif_twice():
    app = TestApp()
    app.doc.date_range = YearRange(date(2007, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/checkbook.qif'))
    app.mw.parse_file_for_import(testdata.filepath('qif/checkbook.qif'))
    return app

@with_app(app_import_checkbook_qif_twice)
def test_import_again(app):
    #Importing when there are already open tabs adds the new tabs to the iwin
    eq_(len(app.iwin.panes), 4)

@with_app(app_import_checkbook_qif_twice)
def test_switch_description_payee_apply_to_all(app):
    app.iwin.swap_type_list.select(SwapType.DescriptionPayee)
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    # the 4th entry is the Hydro Quebec entry
    app.iwin.selected_pane_index = 2
    eq_(app.itable[3].description_import, 'Hydro-Quebec')
    eq_(app.itable[3].payee_import, 'Power Bill')


# ---
def app_import_checkbook_qif_with_existing_txns():
    app = TestApp()
    app.add_account('foo')
    app.show_account()
    app.add_entry(date='01/01/2007', description='first entry', increase='1')
    app.aview.toggle_reconciliation_mode()
    app.etable.toggle_reconciled()
    app.aview.toggle_reconciliation_mode() # commit
    app.add_entry(date='02/01/2007', description='second entry', increase='2')
    app.doc.date_range = YearRange(date(2007, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/checkbook.qif'))
    app.clear_gui_calls()
    app.iwin.selected_target_account_index = 1 # foo
    app.itable.view.check_gui_calls(['refresh'])
    return app

@with_app(app_import_checkbook_qif_with_existing_txns)
def test_import(app):
    # Import happens in the selected target account
    app.iwin.import_selected_pane()
    eq_(app.bsheet.assets.children_count, 3) # did not add a new account
    app.bsheet.selected = app.bsheet.assets[0]
    app.show_account()
    eq_(app.etable_count(), 7) # The entries have been added

@with_app(app_import_checkbook_qif_with_existing_txns)
def test_match_then_import(app):
    # The entry matching has the correct effect on the import
    app.itable.bind(2, 5) # second entry --> 04/02/2007 Transfer 80.00
    app.iwin.import_selected_pane()
    # The merged entry is supposed to be the last because it changed its date
    eq_(app.etable_count(), 6)
    row = app.etable[5]
    eq_(row.date, '04/02/2007')
    eq_(row.description, 'second entry')
    eq_(row.increase, '80.00')


# ---
def app_load_with_ref():
    app = TestApp()
    app.TXNS = [
        {'date': '20/07/2009', 'amount': '1', 'reference': 'txn1'},
        {'date': '20/07/2009', 'amount': '1', 'reference': 'txn1'},
    ]
    app.fake_import('foo', app.TXNS)
    app.iwin.import_selected_pane()
    return app

@with_app(app_load_with_ref)
def test_import_with_same_reference_twice(app):
    # When 2 txns have the same ref in an account, importing a file with the same ref would
    # cause a crash.
    app.fake_import('foo', app.TXNS)
    app.iwin.selected_target_account_index = 1 # no crash

# ---
def app_load_then_import_with_ref(monkeypatch):
    monkeypatch.patch_today(2008, 1, 1)
    app = TestApp()
    app.doc.load_from_xml(testdata.filepath('moneyguru/with_references1.moneyguru'))
    app.mw.parse_file_for_import(testdata.filepath('moneyguru/with_references2.moneyguru'))
    return app

@with_app(app_load_then_import_with_ref)
def test_selected_target_account(app):
    # If a target account's reference matched the imported account, select it
    eq_(app.iwin.selected_target_account_index, 1)


# ---
def app_import_moneyguru_file_with_expense_account():
    app = TestApp()
    app.doc.date_range = YearRange(date(2008, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('moneyguru', 'simple.moneyguru'))
    return app

@with_app(app_import_moneyguru_file_with_expense_account)
def test_account_panes(app):
    # There are only 2 account panes (one for each asset account). the expense account is not there
    eq_(len(app.iwin.panes), 2)
    eq_(app.iwin.panes[0].name, 'Account 1')
    eq_(app.iwin.panes[1].name, 'Account 2')


# ---
def app_import_accountless_qif():
    app = TestApp()
    app.doc.date_range = YearRange(date(2007, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/accountless.qif'))
    return app

@with_app(app_import_accountless_qif)
def test_account_tabs_has_default_account_name(app):
    # The account is just imported as 'Account'
    eq_(len(app.iwin.panes), 1)
    eq_(app.iwin.panes[0].name, 'Account')
    eq_(app.iwin.panes[0].count, 5)


# ---
def app_import_accountless_qif_with_splits():
    app = TestApp()
    app.doc.date_range = YearRange(date(2008, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/accountless_with_splits.qif'))
    return app

@with_app(app_import_accountless_qif_with_splits)
def test_dont_end_up_with_account_tabs_with_bogus_refs(app):
    # Previously, splits referring to account not present in the QIF has a None account
    eq_(len(app.iwin.panes), 1)
    eq_(app.iwin.panes[0].name, 'Account')
    eq_(app.iwin.panes[0].count, 2)

@with_app(app_import_accountless_qif_with_splits)
def test_transfers(app):
    # The transfer splits' account were correctly set
    eq_(len(app.itable), 2)
    eq_(app.itable[0].transfer_import, 'Payment Sent, Fee')
    eq_(app.itable[0].amount_import, '-1000.00')
    eq_(app.itable[1].transfer_import, 'Web Accept Payment Received, Fee')
    eq_(app.itable[1].amount_import, '18.95')

# ---
def app_import_qif_with_empty_accounts():
    # like checkbook.qif, but with 2 extra empty accounts
    app = TestApp()
    app.doc.date_range = YearRange(date(2007, 1, 1))
    app.mw.parse_file_for_import(testdata.filepath('qif/empty_accounts.qif'))
    return app

@with_app(app_import_qif_with_empty_accounts)
def test_empty_account_dont_end_up_in_account_tabs(app):
    # We don't show empty accounts in the import window's tabs
    eq_(len(app.iwin.panes), 2)
    eq_(app.iwin.panes[0].name, 'Account 1')
    eq_(app.iwin.panes[1].name, 'Account 2')


LOW_DATE_FIELDS = [
    {'date': '5/11/2008', 'amount': '1'},
    {'date': '12/01/2009', 'amount': '1'},
    {'date': '01/02/2009', 'amount': '1'},
]

HIGH_DAY_FIELDS = [
    {'date': '02/01/2009', 'amount': '1'},
    {'date': '13/01/2009', 'amount': '1'},
]

HIGH_YEAR_FIELDS = [
    {'date': '02/01/1999', 'amount': '1'},
    {'date': '13/01/1999', 'amount': '1'},
]

# ---
def app_import_txns_with_low_day_fields():
    app = TestApp()
    app.fake_import('foo', LOW_DATE_FIELDS)
    return app

@with_app(app_import_txns_with_low_day_fields)
def test_can_switch_fields_on_low_day(app):
    # all fields can be switched
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    assert app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.DayYear)
    assert app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.MonthYear)
    assert app.iwin.can_perform_swap()

@with_app(app_import_txns_with_low_day_fields)
def test_switch_day_month(app):
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    app.iwin.perform_swap()
    # Dates are sorted after swap
    # Note: This is day/month/year
    eq_(app.itable[0].date_import, '11/05/2008')
    eq_(app.itable[1].date_import, '02/01/2009')
    eq_(app.itable[2].date_import, '01/12/2009')


@with_app(app_import_txns_with_low_day_fields)
def test_switch_day_year(app):
    app.iwin.swap_type_list.select(SwapType.DayYear)
    app.iwin.perform_swap()
    # Dates are sorted after swap
    # Note: This is day/month/year
    eq_(app.itable[0].date_import, '09/02/2001')
    eq_(app.itable[1].date_import, '08/11/2005')
    eq_(app.itable[2].date_import, '09/01/2012')




# ---
def app_import_txns_with_high_day_fields():
    app = TestApp()
    app.fake_import('foo', HIGH_DAY_FIELDS)
    return app

@with_app(app_import_txns_with_high_day_fields)
def test_can_switch_fields_on_high_day(app):
    # the day can't be switched with month
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    assert not app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.DayYear)
    assert app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.MonthYear)
    assert app.iwin.can_perform_swap()


# ---
def app_import_txns_with_high_year_fields():
    app = TestApp()
    app.fake_import('foo', HIGH_YEAR_FIELDS)
    return app

@with_app(app_import_txns_with_high_year_fields)
def test_can_switch_fields_on_high_year(app):
    # the year can't be switched because 99 is too high
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    assert not app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.DayYear)
    assert not app.iwin.can_perform_swap()
    app.iwin.swap_type_list.select(SwapType.MonthYear)
    assert not app.iwin.can_perform_swap()


# ---
def app_import_txn_with_31st_day_in_date():
    # The date 31/07/2009 has a high day, and if we were to swap year and month, we'd be ending up
    # with an invalid date (31/09/2007).
    app = TestApp()
    app.fake_import('foo', [{'date': '31/07/2009', 'amount': '1'}])
    return app

@with_app(app_import_txn_with_31st_day_in_date)
def test_can_switch_fields_with_31st_as_day(app):
    # September has 30 days, so it's impossible to swap the month and the year.
    app.iwin.swap_type_list.select(SwapType.MonthYear)
    assert not app.iwin.can_perform_swap()


# ---
def app_three_imports_two_of_them_with_low_date():
    app = TestApp()
    app.fake_import('foo1', LOW_DATE_FIELDS)
    app.fake_import('foo2', LOW_DATE_FIELDS)
    app.fake_import('foo3', HIGH_DAY_FIELDS)
    return app

@with_app(app_three_imports_two_of_them_with_low_date)
def test_switch_apply_to_all(app):
    # when the 'apply' argument is passed, the swucth happens in all applicable accounts
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    app.iwin.selected_pane_index = 1
    eq_(app.itable[0].date_import, '11/05/2008') # switched
    app.iwin.selected_pane_index = 2
    eq_(app.itable[0].date_import, '02/01/2009') # not switched


# ---
def app_two_accounts_with_common_txn():
    app = TestApp()
    txns = [
        {
            'date': '5/11/2008',
            'transfer': 'second',
            'description':'foo',
            'payee': 'bar',
            'amount': '1',
        },
    ]
    loader = DictLoader(app.doc.default_currency, 'first', txns)
    loader.start_account()
    loader.account_info.name = 'second'
    loader.flush_account()
    loader.load()
    app.mw.loader = loader
    app.iwin.show()
    return app

@with_app(app_two_accounts_with_common_txn)
def test_switch_date_with_common_txn(app):
    # the transaction in the 2 accounts is the same. *don't* switch it twice!
    app.iwin.swap_type_list.select(SwapType.DayMonth)
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    eq_(app.itable[0].date_import, '11/05/2008')

@with_app(app_two_accounts_with_common_txn)
def test_switch_description_payee_with_common_txn(app):
    # same as with dates: don't switch twice
    app.iwin.swap_type_list.select(SwapType.DescriptionPayee)
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    eq_(app.itable[0].description_import, 'bar')
    eq_(app.itable[0].payee_import, 'foo')


# ---
def app_with_structure_change_import_plugin():
    app = TestApp()
    app.set_plugins([ChangeStructure])

    txns = [
        {
            'date': '01/13/2014',
            'transfer': 'x',
            'description': 'foo',
            'payee': 'bar',
            'amount': '-1.00'
        },
        {
            'date': '12/10/2014',
            'transfer': 'x',
            'description': 'bar',
            'payee': 'bar',
            'amount': '0.00'
        },
        {
            'date': '12/10/2014',
            'transfer': 'x',
            'description': 'baz',
            'payee': 'bar',
            'amount': '1.00'
        }
    ]

    loader = DictLoader(app.doc.default_currency, 'first', txns)
    loader.start_account()
    loader.account_info.name = 'second'
    loader.flush_account()
    loader.load()
    app.mw.loader = loader
    app.iwin.show()
    return app

@with_app(app_with_structure_change_import_plugin)
def test_change_split_structure(app):
    # same as with dates: don't switch twice
    swap_list = app.iwin.swap_type_list
    eq_(app.iwin.swap_type_list[-1], ChangeStructure.ACTION_NAME)
    swap_list.select(-1)
    eq_(app.itable[0].transfer_import, 'x')
    eq_(app.itable[0].amount_import, '-1.00')
    eq_(app.itable[1].transfer_import, 'x')
    eq_(app.itable[1].amount_import, '0.00')
    eq_(app.itable[2].transfer_import, 'x')
    eq_(app.itable[2].amount_import, '1.00')
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    eq_(app.itable[0].transfer_import, 'x, imbalance account')
    eq_(app.itable[0].amount_import, '0.00')
    eq_(app.itable[1].transfer_import, 'x, imbalance account')
    eq_(app.itable[1].amount_import, '1.00')
    eq_(app.itable[2].transfer_import, 'x, imbalance account')
    eq_(app.itable[2].amount_import, '2.00')


# ---
def app_import_checkbook_qif_with_existing_txns_and_change_import_plugin():
    app = app_import_checkbook_qif_with_existing_txns()
    app.set_plugins([ChangeStructure])
    return app

@with_app(app_import_checkbook_qif_with_existing_txns_and_change_import_plugin)
def test_match_then_run_plugin_that_calls_change_transaction(app):
    # We do the exact same thing as in test_match_then_import, but we run a plugin that calls
    # change_transaction() first to verify that we don't break the bindings.
    eq_(app.itable.row_count, 6) # we start with 6 lines
    app.itable.bind(2, 5)
    eq_(app.itable.row_count, 5) # because of the binding, we have 5 lines
    app.iwin.swap_type_list.select(-1)
    app.iwin.perform_swap(apply=ActionSelectionOptions.ApplyToAll)
    eq_(app.itable.row_count, 5) # we still have 5 lines because the binding wasn't broken.


# ---
def app_with_transfer_change_import_plugin():
    app = TestApp()
    app.set_plugins([ChangeTransfer])

    txns = [
        {
            'date': '12/09/2014',
            'transfer': 'AUTOMATIC PAYMENT - THANK YOU',
            'description': 'foo',
            'payee': 'bar',
            'amount': '-3.21'
        },
        {
            'date': '12/10/2014',
            'transfer': 'PAYMENT AUTOMATICALLY RECEIVED',
            'description': 'foo',
            'payee': 'bar',
            'amount': '-20.22'
        },
        {
            'date': '12/10/2014',
            'transfer': 'GAS',
            'description': 'foo',
            'payee': 'bar',
            'amount': '20.23'
        }
    ]

    loader = DictLoader(app.doc.default_currency, 'first', txns)
    loader.start_account()
    loader.account_info.name = 'second'
    loader.flush_account()
    loader.load()
    app.mw.loader = loader
    app.iwin.show()
    return app

@with_app(app_with_transfer_change_import_plugin)
def test_switch_transfer_accounts(app):
    # Our action name is not manually selectable (since it is an always_perform)
    assert ChangeTransfer.ACTION_NAME not in app.iwin.swap_type_list
    eq_(app.itable[0].transfer_import, 'checking')
    eq_(app.itable[1].transfer_import, 'checking')
    eq_(app.itable[2].transfer_import, 'GAS')

