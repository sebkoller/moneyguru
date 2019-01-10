# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..testutil import eq_

from ..base import TestApp, with_app

# --- Pristine
def test_can_navigate():
    # The `can_navigate` property mirrors the date range's `can_navigate`.
    app = TestApp() # year range
    assert app.drsel.can_navigate
    app.drsel.select_year_to_date_range()
    assert not app.drsel.can_navigate

# --- Saved custom range
def app_saved_custom_range():
    app = TestApp()
    app.drsel.invoke_custom_range_panel()
    cdrpanel = app.get_current_panel()
    cdrpanel.start_date = '27/02/2010'
    cdrpanel.end_date = '17/03/2010'
    cdrpanel.slot_index = 2
    cdrpanel.slot_name = 'foo'
    cdrpanel.save()
    # Select another range
    app.drsel.select_month_range()
    return app

@with_app(app_saved_custom_range)
def test_saved_ranges_are_persistent(app):
    # Saved ranges are saved to preferences
    newapp = app.new_app_same_prefs()
    eq_(newapp.drsel.custom_range_names, [None, 'foo', None])
    app.drsel.select_saved_range(1)
    eq_(app.drsel.display, '27/02/2010 - 17/03/2010')

@with_app(app_saved_custom_range)
def test_restore_saved_range(app):
    # It's possible to restore saved custom ranges
    app.drsel.select_saved_range(1)
    eq_(app.drsel.display, '27/02/2010 - 17/03/2010')

@with_app(app_saved_custom_range)
def test_restore_null_saved_range(app):
    # Trying to restore null saved range doesn't cause a crash
    app.drsel.select_saved_range(0) # no crash
