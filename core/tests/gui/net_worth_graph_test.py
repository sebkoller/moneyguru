# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date

from ..testutil import eq_

from ..base import TestApp, with_app, testdata
from ...model.account import AccountType
from ...model.currency import Currencies

class TestAssetsAndLiabilitiesInDifferentAccounts:
    def do_setup(self):
        app = TestApp()
        app.drsel.select_month_range()
        for i in range(1, 15):
            Currencies.get_rates_db().set_CAD_value(date(2008, 7, i), 'USD', 1.42)
        for i in range(15, 32):
            Currencies.get_rates_db().set_CAD_value(date(2008, 7, i), 'USD', 1.54)
        app.add_account('asset1')
        app.show_account()
        app.add_entry('12/6/2008', increase='10') # previous balance
        app.add_entry('3/7/2008', increase='50')
        app.add_entry('5/7/2008', increase='80')
        app.add_account('asset2')
        app.show_account()
        app.add_entry('1/7/2008', increase='32')
        app.add_entry('5/7/2008', increase='22')
        app.add_account('liability1', 'CAD', account_type=AccountType.Liability)
        app.show_account()
        app.add_entry('1/7/2008', increase='10')
        app.add_account('liability2', account_type=AccountType.Liability)
        app.show_account()
        app.add_entry('8/7/2008', increase='100')
        app.show_nwview()
        app.clear_gui_calls()
        return app

    @with_app(do_setup)
    def test_add_group(self, app):
        # There was previously a bug where adding a group would empty the graph up.
        app.bsheet.add_account_group()
        app.bsheet.selected.name = 'foo'
        app.bsheet.save_edits()
        assert app.nw_graph_data()

    @with_app(do_setup)
    def test_budget(self, app, monkeypatch):
        # when we add a budget, the balance graph will show a regular
        # progression throughout date range
        monkeypatch.patch_today(2008, 7, 27)
        app.add_account('income', account_type=AccountType.Income)
        app.add_account('expense', account_type=AccountType.Expense)
        app.add_budget('income', '300')
        app.add_budget('expense', '100')
        app.show_nwview()
        # this means 200$ profit in 4 days
        app.show_nwview()
        expected = [
            ('01/07/2008', '10.00'),
            ('02/07/2008', '34.96'), # 32 - 10 * 1.42 (the mock xchange rate)
            ('03/07/2008', '34.96'),
            ('04/07/2008', '84.96'), # + 50
            ('05/07/2008', '84.96'),
            ('06/07/2008', '186.96'), # + 80 + 22
            ('08/07/2008', '186.96'),
            ('09/07/2008', '86.96'), # - 100
            ('15/07/2008', '86.96'),
            ('16/07/2008', '87.51'), # currency value change
            ('28/07/2008', '87.51'),
            ('01/08/2008', '287.51'),
        ]
        eq_(app.nw_graph_data(), expected)

    @with_app(do_setup)
    def test_exclude_account(self, app):
        # excluding an account removes it from the net worth graph
        app.bsheet.selected = app.bsheet.liabilities[0] # that CAD account
        app.bsheet.toggle_excluded()
        expected = [
            ('01/07/2008', '10.00'),
            ('02/07/2008', '42.00'),
            ('03/07/2008', '42.00'),
            ('04/07/2008', '92.00'), # + 50
            ('05/07/2008', '92.00'),
            ('06/07/2008', '194.00'), # + 80 + 22
            ('08/07/2008', '194.00'),
            ('09/07/2008', '94.00'), # - 100
            ('01/08/2008', '94.00'),
        ]
        eq_(app.nw_graph_data(), expected)
        app.check_gui_calls(app.nwgraph_gui, ['refresh'])

    @with_app(do_setup)
    def test_net_worth_graph(self, app):
        # One interesting thing about this graph is that on the 14th of july, the CAD value changes,
        # so even if there is no entry on that day, the net worth changes anyway.
        expected = [
            ('01/07/2008', '10.00'),
            ('02/07/2008', '34.96'), # 32 - 10 * 1.42 (the mock xchange rate)
            ('03/07/2008', '34.96'),
            ('04/07/2008', '84.96'), # + 50
            ('05/07/2008', '84.96'),
            ('06/07/2008', '186.96'), # + 80 + 22
            ('08/07/2008', '186.96'),
            ('09/07/2008', '86.96'), # - 100
            ('15/07/2008', '86.96'),
            ('16/07/2008', '87.51'), # currency value change
            ('01/08/2008', '87.51'),
        ]
        eq_(app.nw_graph_data(), expected)
        eq_(app.nwgraph.title, 'Net Worth')
        eq_(app.nwgraph.currency, 'USD')

    @with_app(do_setup)
    def test_refresh_account_deleted(self, app):
        # When an account is deleted, charts are refreshed
        app.bsheet.selected = app.bsheet.assets[0]
        app.bsheet.delete()
        arpanel = app.get_current_panel()
        arpanel.save() # continue deletion
        assert app.nw_graph_data()[0] != ('01/07/2008', '10.00')
        app.check_gui_calls(app.nwgraph_gui, ['refresh'])

    @with_app(do_setup)
    def test_refresh_on_import(self, app):
        # When entries are imported, charts are refreshed
        iwin = app.mw.parse_file_for_import(testdata.filepath('qif', 'checkbook.qif'))
        iwin.import_selected_pane()
        # For the data itself, we just have to test that it changed. the QIF has data in 02/2008
        assert app.nw_graph_data()[0] != ('01/07/2008', '10.00')
        app.check_gui_calls(app.nwgraph_gui, ['refresh'])

