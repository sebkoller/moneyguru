# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from ..testutil import eq_

from ..base import TestApp, with_app, ApplicationGUI
from ...app import Application
from ...model.account import AccountType
from ...model.currency import Currencies
from ...model.date import MonthRange

# ---
def app_pristine():
    app = TestApp()
    app.show_pview()
    app.check_gui_calls(app.istatement_gui, ['refresh'])
    return app

@with_app(app_pristine)
def test_add_account_in_other_groups(app):
    # When groups other than Assets are selected, new accounts go underneath it.
    app.istatement.selected = app.istatement.expenses
    app.istatement.add_account()
    eq_(app.istatement.selected, app.istatement.expenses[0])
    app.istatement.add_account()
    eq_(app.istatement.selected, app.istatement.expenses[1])
    app.istatement.selected = app.istatement.income
    app.istatement.add_account()
    eq_(app.istatement.selected, app.istatement.income[0])
    app.istatement.add_account()
    eq_(app.istatement.selected, app.istatement.income[1])
    app.istatement.selected = None
    app.istatement.add_account()
    eq_(app.istatement.selected, app.istatement.income[2])

@with_app(app_pristine)
def test_income_statement_pristine(app):
    # The income statement is empty.
    eq_([x.name for x in app.istatement], ['INCOME', 'EXPENSES', 'NET INCOME'])

@with_app(app_pristine)
def test_nodes_are_hashable(app):
    # Just make sure it's possible to put the nodes in containers based on hashes.
    eq_(len({app.istatement.income, app.istatement.expenses}), 2) # no crash

# ---
def app_accounts_and_entries():
    app = TestApp()
    app.drsel.select_month_range()
    app.add_account('Account 1', account_type=AccountType.Income)
    app.show_account()
    app.add_entry('10/01/2008', 'Entry 1', increase='100.00')
    app.add_entry('13/01/2008', 'Entry 2', increase='150.00')
    app.add_account('Account 2', account_type=AccountType.Income)
    app.show_account()
    app.add_entry('11/12/2007', 'Entry 3', increase='100.00')
    app.add_entry('12/01/2008', 'Entry 4', decrease='20.00')
    app.show_pview()
    return app

@with_app(app_accounts_and_entries)
def test_add_entry(app):
    # adding an entry updates the cache flow (previously, the cache wouldn't be correctly invalidated)
    app.istatement.selected = app.istatement.income[0]
    app.show_account()
    app.add_entry('13/01/2008', 'Entry 3', increase='42.00')
    app.show_pview()
    eq_(app.istatement.income[0].cash_flow, '292.00')

@with_app(app_accounts_and_entries)
def test_attrs_with_budget(app, monkeypatch):
    # Must include the budget. 250 of the 400 are spent, there's 150 left to add
    monkeypatch.patch_today(2008, 1, 17)
    app.add_budget('Account 1', '400')
    app.show_pview()
    eq_(app.istatement.income[0].cash_flow, '250.00')
    eq_(app.istatement.income[0].budgeted, '150.00')
    eq_(app.istatement.income.budgeted, '150.00')
    eq_(app.istatement.net_income.budgeted, '150.00')
    app.drsel.select_next_date_range()
    eq_(app.istatement.income[0].cash_flow, '0.00')
    eq_(app.istatement.income[0].budgeted, '400.00')
    app.drsel.select_quarter_range()
    eq_(app.istatement.income[0].cash_flow, '250.00')
    eq_(app.istatement.income[0].budgeted, '950.00')
    app.drsel.select_year_range()
    eq_(app.istatement.income[0].cash_flow, '250.00')
    eq_(app.istatement.income[0].budgeted, '4550.00')
    app.drsel.select_year_to_date_range()
    eq_(app.istatement.income[0].cash_flow, '250.00')

@with_app(app_accounts_and_entries)
def test_cash_flow_with_underestimated_budget(app, monkeypatch):
    monkeypatch.patch_today(2008, 1, 17)
    app.add_budget('Account 1', '200')
    app.show_pview()
    eq_(app.istatement.income[0].cash_flow, '250.00')

@with_app(app_accounts_and_entries)
def test_exclude_account(app):
    # Excluding an account removes its amount from the totals and blanks its own amounts
    app.istatement.selected = app.istatement.income[1]
    app.istatement.toggle_excluded()
    eq_(app.istatement.income[1].cash_flow, '')
    eq_(app.istatement.income[1].last_cash_flow, '')
    eq_(app.istatement.income[1].delta, '')
    eq_(app.istatement.income[1].delta_perc, '')
    eq_(app.istatement.income.cash_flow, '250.00')
    eq_(app.istatement.income.last_cash_flow, '0.00')
    eq_(app.istatement.income.delta, '250.00')
    eq_(app.istatement.income.delta_perc, '---')

@with_app(app_accounts_and_entries)
def test_income_statement_with_accounts_and_entries(app):
    eq_(app.doc.date_range, MonthRange(date(2008, 1, 1)))
    eq_(app.istatement.income[0].name, 'Account 1')
    eq_(app.istatement.income[0].cash_flow, '250.00')
    eq_(app.istatement.income[1].name, 'Account 2')
    eq_(app.istatement.income[1].cash_flow, '-20.00')
    eq_(app.istatement.income.cash_flow, '230.00')

@with_app(app_accounts_and_entries)
def test_set_custom_date_range(app):
    # same problem as test_year_to_date_last_cash_flow
    cdrpanel = app.drsel.invoke_custom_range_panel()
    cdrpanel.start_date = '01/01/2008'
    cdrpanel.start_date = '12/12/2008'
    cdrpanel.save()
    eq_(app.istatement.income[0].last_cash_flow, '0.00')

@with_app(app_accounts_and_entries)
def test_year_to_date_last_cash_flow(app, monkeypatch):
    # When the YTD range is selected, the "Last" column shows last year's value (here, 0) instead
    # of showing the exact same thing as this period.
    monkeypatch.patch_today(2008, 12, 12)
    app.drsel.select_year_to_date_range()
    eq_(app.istatement.income[0].last_cash_flow, '0.00')

# ---
def app_multiple_currencies():
    app = TestApp(app=Application(ApplicationGUI(), default_currency='CAD'))
    app.drsel.select_month_range()
    Currencies.get_rates_db().set_CAD_value(date(2008, 1, 1), 'USD', 0.8)
    Currencies.get_rates_db().set_CAD_value(date(2008, 1, 31), 'USD', 0.9)
    app.add_group('Group', account_type=AccountType.Income)
    app.add_account('CAD account', currency='CAD', account_type=AccountType.Income, group_name='Group')
    app.show_account()
    app.add_entry('1/1/2008', 'USD entry', increase='100.00')
    app.add_account('USD account', currency='USD', account_type=AccountType.Income, group_name='Group')
    app.show_account()
    app.add_entry('1/1/2007', 'USD entry', increase='50.00')
    app.add_entry('1/1/2008', 'USD entry', increase='80.00')
    app.add_entry('31/1/2008', 'USD entry', increase='20.00')
    app.show_pview()
    return app

@with_app(app_multiple_currencies)
def test_with_budget(app, monkeypatch):
    # What this test is making sure of is that the account's budget is of the same currency than
    # the account itself
    monkeypatch.patch_today(2008, 1, 20)
    app.add_budget('USD account', '300usd')
    app.show_pview()
    eq_(app.istatement.income[0][1].cash_flow, 'USD 100.00')
    eq_(app.istatement.income[0][1].budgeted, 'USD 200.00')

@with_app(app_multiple_currencies)
def test_income_statement_multiple_currencies(app):
    # Each income/expense transaction is converted using the day's rate.
    # Also, every amount show their currency explicitly. Ref #392
    eq_(app.doc.date_range, MonthRange(date(2008, 1, 1)))
    eq_(app.istatement.income[0][0].cash_flow, '100.00')
    eq_(app.istatement.income[0][1].cash_flow, 'USD 100.00')
    eq_(app.istatement.income[0].cash_flow, 'CAD 182.00')   # 80 * .8 + 20 * .9 + 100
    eq_(app.istatement.income.cash_flow, 'CAD 182.00')

# ---
def app_multiple_currencies_over_two_months():
    app = TestApp(app=Application(ApplicationGUI(), default_currency='CAD'))
    app.drsel.select_month_range()
    Currencies.get_rates_db().set_CAD_value(date(2008, 1, 1), 'USD', 0.8)
    Currencies.get_rates_db().set_CAD_value(date(2008, 1, 31), 'USD', 0.9)
    Currencies.get_rates_db().set_CAD_value(date(2008, 2, 10), 'USD', 0.9)
    app.add_account('CAD account', currency='CAD', account_type=AccountType.Income)
    app.show_account()
    app.add_entry('1/1/2008', 'CAD entry', increase='200.00')
    app.add_entry('1/2/2008', 'CAD entry', increase='190.00')
    app.add_account('USD account', currency='USD', account_type=AccountType.Expense)
    app.show_account()
    app.add_entry('1/1/2008', 'USD entry', increase='50.00')
    app.add_entry('1/1/2008', 'USD entry', increase='80.00')
    app.add_entry('31/1/2008', 'USD entry', increase='20.00')
    app.add_entry('10/2/2008', 'USD entry', increase='100.00')
    app.show_pview()
    return app

@with_app(app_multiple_currencies_over_two_months)
def test_income_statement_multiple_currencies_over_two_months(app):
    # the last_cach_flow and deltas are correct
    eq_(app.istatement.income[0].cash_flow, '190.00')
    eq_(app.istatement.income[0].last_cash_flow, '200.00')
    eq_(app.istatement.income[0].delta, '-10.00')
    eq_(app.istatement.income[0].delta_perc, '-5.0%')
    eq_(app.istatement.expenses[0].cash_flow, 'USD 100.00')
    eq_(app.istatement.expenses[0].last_cash_flow, 'USD 150.00')
    eq_(app.istatement.expenses[0].delta, 'USD -50.00')
    eq_(app.istatement.expenses[0].delta_perc, '-33.3%')
    eq_(app.istatement.expenses.cash_flow, 'CAD 90.00')   # 100 * .9
    eq_(app.istatement.expenses.last_cash_flow, 'CAD 122.00')   # 130 * .8 + 20 * .9
    eq_(app.istatement.expenses.delta, 'CAD -32.00')   # 130 * .8 + 20 * .9
    eq_(app.istatement.expenses.delta_perc, '-26.2%')
    eq_(app.istatement.net_income.cash_flow, 'CAD 100.00')
    eq_(app.istatement.net_income.last_cash_flow, 'CAD 78.00')
    eq_(app.istatement.net_income.delta, 'CAD 22.00')
    eq_(app.istatement.net_income.delta_perc, '+28.2%')

# ---
def app_entries_spread_over_a_year():
    app = TestApp()
    app.add_account('Account', account_type=AccountType.Income)
    app.show_account()
    app.add_entry('01/01/2007', 'Entry', increase='1')
    app.add_entry('01/04/2007', 'Entry', increase='2')
    app.add_entry('01/08/2007', 'Entry', increase='3')
    app.add_entry('01/12/2007', 'Entry', increase='4')
    app.add_entry('01/01/2008', 'Entry', increase='5')
    app.add_entry('01/04/2008', 'Entry', increase='6')
    app.add_entry('01/08/2008', 'Entry', increase='7')
    app.add_entry('01/12/2008', 'Entry', increase='8')
    app.add_entry('01/03/2009', 'Entry', increase='9')
    app.add_entry('01/05/2009', 'Entry', increase='10')
    app.show_pview()
    return app

@with_app(app_entries_spread_over_a_year)
def test_select_running_year_range(app, monkeypatch):
    # the 'Last' column will correctly be set and will include amounts from a whole year before
    # the start of the running year.
    monkeypatch.patch_today(2008, 12, 1)
    app.drsel.select_running_year_range()
    # ahead_months is 2, so current is 01/03/2008-28/02/2009, which means 6 + 7 + 8 (21)
    eq_(app.istatement.income[0].cash_flow, '21.00')
    # 'Last' is 01/03/2007-28/02/2008, which means 2 + 3 + 4 + 5 (14)
    eq_(app.istatement.income[0].last_cash_flow, '14.00')

# ---
def app_busted_budget(monkeypatch):
    monkeypatch.patch_today(2010, 1, 3)
    app = TestApp()
    app.drsel.select_month_range()
    app.add_account('account', account_type=AccountType.Income)
    app.show_account()
    app.add_entry('01/01/2010', increase='112')
    app.add_budget('account', '100')
    app.show_pview()
    return app

@with_app(app_busted_budget)
def test_budget_column_display(app):
    # The budget column displays 0
    eq_(app.istatement.income[0].budgeted, '0.00')

