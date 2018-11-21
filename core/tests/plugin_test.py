# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from hscommon.testutil import eq_
from core.plugin import CurrencyProviderPlugin, ViewPlugin

from ..model.currency import Currencies
from ..const import PaneType
from .base import TestApp, with_app

def find_pview_row(pview, name):
    for row in pview.table:
        if row.name == name:
            return row
    else:
        raise AssertionError("can't find {} row".format(name))

def get_plugin_list(app):
    app.mw.select_pane_of_type(PaneType.Empty)
    eview = app.current_view()
    return eview.plugin_list

@with_app(TestApp)
def test_dont_crash_with_duplicate_currency_register(app):
    # When two currency plugins register the same currency, don't crash, just ignore the second.
    # XXX At the time of this writing, this test is kinda broken because currency registering,
    # which is global, is not re-initialized after each test, so the test passes, but for dubious
    # reasons (the code that makes this test pass, if removed, breaks all tests). I'll refactor
    # currencies shortly to fix this.
    class FooCurrencyProvider(CurrencyProviderPlugin):
        NAME = "Foo currency fetcher"
        PRIORITY = 1
        def register_currencies(self):
            return [('XXX', "Foo", 2, 1)]

    class BarCurrencyProvider(CurrencyProviderPlugin):
        NAME = "Bar currency fetcher"
        PRIORITY = 2
        def register_currencies(self):
            return [('XXX', "Bar", 2, 1)]

    app.set_plugins([FooCurrencyProvider, BarCurrencyProvider]) # no crash
    assert 'XXX - Foo' in Currencies.display_list()

@with_app(TestApp)
def test_ignore_duplicate_plugin_names(app):
    # If two plugins have the same name, don't register the second.

    class FooPlugin(ViewPlugin):
        NAME = "Foo"

    class BarPlugin(ViewPlugin):
        NAME = "Foo"

    app.set_plugins([FooPlugin, BarPlugin])
    emptyview = app.new_tab()
    eq_(len(emptyview.plugin_list), 1) # Only one plugin was loaded

def test_dont_crash_on_missing_appdata_path(tmpdir):
    # When the "appdata" path doesn't exist, don't crash on startup. ref #437
    appdata = str(tmpdir.join('appdata'))
    TestApp(appargs={'appdata_path': appdata}) # no crash

@with_app(TestApp)
def test_enabled_disable_view_plugin(app):
    # Enabling/Disabling a view plugin removes it from the plugin view list. ref #451
    app.mw.select_pane_of_type(PaneType.PluginList)
    pview = app.current_view()
    row = find_pview_row(pview, 'Account List')
    assert not row.enabled
    assert 'Account List' not in get_plugin_list(app)
    row.enabled = True
    assert 'Account List' in get_plugin_list(app.new_app_same_prefs())
    row.enabled = False
    assert 'Account List' not in get_plugin_list(app.new_app_same_prefs())

@with_app(TestApp)
def test_disable_currency_plugin(app):
    # Disabling a currency plugin makes currencies it provides unavailable. ref #451
    app.mw.select_pane_of_type(PaneType.PluginList)
    pview = app.current_view()
    row = find_pview_row(pview, 'Stale currencies provider')
    assert row.enabled
    row.enabled = False
    Currencies.reset_currencies()
    newapp = app.new_app_same_prefs()
    tview = newapp.show_tview()
    newapp.add_txn(amount='42 ats')
    # ATS, not being supported is replaced by our default currency
    eq_(tview.ttable[0].amount, '42.00')

