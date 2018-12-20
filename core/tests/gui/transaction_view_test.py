# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from ..testutil import eq_

from ...model.currency import Currencies
from ..base import TestApp, with_app

# --- three transactions
def app_three_transactions():
    app = TestApp()
    app.add_txn(amount='1')
    app.add_txn(amount='2')
    app.add_txn(amount='3')
    return app

@with_app(app_three_transactions)
def test_totals_select_one(app):
    # the totals line shows the number of selected transactions
    expected = "1 out of 3 selected. Amount: 3.00"
    eq_(app.mw.status_line, expected)

@with_app(app_three_transactions)
def test_totals_select_two(app):
    # when two transactions are selected, the totals line changes
    app.ttable.select([1, 2])
    expected = "2 out of 3 selected. Amount: 5.00"
    eq_(app.mw.status_line, expected)

# --- Multiple currencies
def app_multiple_currencies():
    app = TestApp()
    Currencies.get_rates_db().set_CAD_value(date(2010, 3, 9), 'USD', 2)
    app.add_txn('10/03/2010', amount='10')
    app.add_txn('10/03/2010', amount='10 CAD') # worth 5usd
    return app

@with_app(app_multiple_currencies)
def test_totals_select_all(app):
    # Foreign amounts are converted
    app.ttable.select([0, 1])
    expected = "2 out of 2 selected. Amount: 15.00"
    eq_(app.mw.status_line, expected)
