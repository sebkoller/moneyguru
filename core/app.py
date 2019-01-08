# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os
import os.path as op
import datetime
from collections import namedtuple
import re

from core.util import nonone

from .gui.date_widget import DateWidget

from . import __version__
from .const import DATE_FORMAT_FOR_PREFERENCES
from .model import currency
from .model.amount import parse_amount, format_amount
from .model.currency import Currencies
from .model.date import parse_date, format_date
from .plugin import CurrencyProviderPlugin, get_all_core_plugin_modules, get_plugins_from_mod

class PreferenceNames:
    """Holds a list of preference key constants used in moneyGuru.

    * ``HadFirstLaunch``
    * ``AutoSaveInterval``
    * ``AutoDecimalPlace``
    * ``CustomRanges``
    * ``ShowScheduleScopeDialog``
    """
    HadFirstLaunch = 'HadFirstLaunch'
    AutoSaveInterval = 'AutoSaveInterval'
    AutoDecimalPlace = 'AutoDecimalPlace'
    DayFirstDateEntry = 'DayFirstDateEntry'
    CustomRanges = 'CustomRanges'
    ShowScheduleScopeDialog = 'ShowScheduleScopeDialog'

# http://stackoverflow.com/questions/1606436/adding-docstrings-to-namedtuples-in-python
class SavedCustomRange(namedtuple('SavedCustomRange', 'name start end')):
    """*namedtuple*. Holds attributes for moneyGuru's saved custom date ranges.

    .. seealso:: :class:`core.model.date.CustomDateRange`

    .. attribute:: name

        Name of the range

    .. attribute:: start

        *date*. Start of the range

    .. attribute:: end

        *date*. End of the range
    """
    __slots__ = ()

class ApplicationView:
    """Expected interface for :class:`Application`'s view.

    *Not actually used in the code. For documentation purposes only.*

    Our view here isn't materialize visually, but rather is a entry point to calls that are
    OS-specific, like preferences access and opening URLs and paths.
    """
    def get_default(self, key_name):
        """Returns the preference value for ``key_name``.

        That preference is specific to the running application, for the current user. For example,
        if ``key_name`` is ``foobar``, we expect to be returned the value corresponding to that key
        for moneyGuru, and for the user currently running it.

        The return value type can be pretty much anything that is serializable. ``str``, ``int``,
        ``float``, ``bool``, ``list``, ``dict``. Some other types are possible, but we're trying to
        limit ourselves to these.

        :param str key_name: The key name of the preference we want to retrieve.
        """

    def set_default(self, key_name, value):
        """Sets the preference ``key_name`` to ``value``.

        .. seealso:: :meth:`get_default`.
        """

    def show_message(self, msg):
        """Pops up a modal dialog with ``msg`` as a message, and a OK button."""

    def open_url(self, url):
        """Open ``url`` with the system's default URL handler."""

    def reveal_path(self, path):
        """Open ``path`` with the system's default file explorer."""

class Application:
    """Manage a running instance of moneyGuru.

    Mostly, it handles app-wide user preferences. It doesn't hold a reference to a list of open
    :class:`.Document` instances. These instances are auto-sufficient and their reference are held
    directly by the UI layer.

    But otherwise, it acts as an app-wide preference repository. As such, it provides useful
    utilities, such as :meth:`format_amount`, :meth:`format_date`, :meth:`parse_amount` and
    :meth:`parse_date`, which are dependent on user preferences.

    Its initialization arguments are such preferences.

    :param view: An OS-specific outlet from the UI layer.
    :type view: :class:`ApplicationView`
    :param str date_format: The date format to use throughout the app. "ISO" format type (see
                            :class:`.DateFormat` on that topic).
    :param str decimal_sep: Decimal separator to use when formatting/parsing amounts.
    :param str grouping_sep: Thousands grouping separator to use when formatting/parsing amounts.
    :param default_currency: Most of the time, we have more precise default currency values to use
                             than this one (account level, document level), but when all else fail
                             use this currency when parsing an amount for which we don't know the
                             currency.
    :type default_currency: :class:`.Currency`
    :param str cache_path: The path (a folder) in which we put our "cache" stuff, that is, the
                           SQLite currency rate cache DB and autosaved files. If ``None``, the
                           currency cache will be in-memory and autosaves will not happen.
    :param str appdata_path: Path in which we put user-specific files we need for moneyGuru to work
                             well, but that don't qualify as "cache". For now, it's where we put
                             the plugins. If ``None``, plugins are disabled.
    """

    APP_NAME = "moneyGuru"
    PROMPT_NAME = APP_NAME
    NAME = APP_NAME
    VERSION = __version__

    def __init__(
            self, view, date_format='dd/MM/yyyy', decimal_sep='.', grouping_sep='',
            default_currency='USD', cache_path=None, appdata_path=None):
        self.view = view
        self.cache_path = cache_path
        # cache_path is required, but for tests, we don't want to bother specifying it. When
        # cache_path is kept as None, the path of the currency db will be ':memory:'
        if cache_path:
            if not op.exists(cache_path):
                os.makedirs(cache_path)
            db_path = op.join(cache_path, 'currency.db')
        else:
            db_path = ':memory:'
        self.appdata_path = appdata_path
        if appdata_path and not op.exists(appdata_path):
            os.makedirs(appdata_path)
        currency.initialize_db(db_path)
        self.is_first_run = not self.get_default(PreferenceNames.HadFirstLaunch, False)
        if self.is_first_run:
            self.set_default(PreferenceNames.HadFirstLaunch, True)
        self._default_currency = default_currency
        self._date_format = date_format
        self._decimal_sep = decimal_sep
        self._grouping_sep = grouping_sep
        self._autosave_interval = self.get_default(PreferenceNames.AutoSaveInterval, 10)
        self._auto_decimal_place = self.get_default(PreferenceNames.AutoDecimalPlace, False)
        self._day_first_date_entry = self.get_default(PreferenceNames.DayFirstDateEntry, True)
        self._show_schedule_scope_dialog = self.get_default(PreferenceNames.ShowScheduleScopeDialog, True)
        self.saved_custom_ranges = [None] * 3
        self._load_custom_ranges()
        self.plugins = []
        self._load_core_plugins()
        self._hook_currency_plugins()
        self._update_date_entry_order()

    # --- Private
    def _update_date_entry_order(self):
        DateWidget.setDMYEntryOrder(self._day_first_date_entry)

    def _load_custom_ranges(self):
        custom_ranges = self.get_default(PreferenceNames.CustomRanges)
        if not custom_ranges:
            return
        for index, custom_range in enumerate(custom_ranges):
            if custom_range:
                name = custom_range[0]
                start = datetime.datetime.strptime(custom_range[1], DATE_FORMAT_FOR_PREFERENCES).date()
                end = datetime.datetime.strptime(custom_range[2], DATE_FORMAT_FOR_PREFERENCES).date()
                self.saved_custom_ranges[index] = SavedCustomRange(name, start, end)
            else:
                self.saved_custom_ranges[index] = None

    def _load_plugin_module(self, plugin_module):
        for x in get_plugins_from_mod(plugin_module):
            if all(p.NAME != x.NAME for p in self.plugins):
                self.plugins.append(x)

    def _load_core_plugins(self):
        for mod in get_all_core_plugin_modules():
            self._load_plugin_module(mod)

    def _hook_currency_plugins(self):
        currency_plugins = [p for p in self.get_enabled_plugins() if issubclass(p, CurrencyProviderPlugin)]
        for p in currency_plugins:
            Currencies.get_rates_db().register_rate_provider(p().wrapped_get_currency_rates)

    def _save_custom_ranges(self):
        custom_ranges = []
        for custom_range in self.saved_custom_ranges:
            if custom_range:
                start_str = custom_range.start.strftime(DATE_FORMAT_FOR_PREFERENCES)
                end_str = custom_range.end.strftime(DATE_FORMAT_FOR_PREFERENCES)
                custom_ranges.append([custom_range.name, start_str, end_str])
            else:
                # We can't insert None in arrays for preferences
                custom_ranges.append([])
        self.set_default(PreferenceNames.CustomRanges, custom_ranges)

    # --- Public
    def format_amount(self, amount, **kw):
        """Returns a formatted amount using app-wide preferences.

        This simply wraps :func:`core.model.amount.format_amount` and adds default values.
        """
        return format_amount(amount, self._default_currency, decimal_sep=self._decimal_sep,
                             grouping_sep=self._grouping_sep, **kw)

    def format_date(self, date):
        """Returns a formatted date using app-wide preferences.

        This simply wraps :func:`core.model.date.format_date` and adds default values.
        """
        return format_date(date, self._date_format)

    def parse_amount(self, amount, default_currency=None):
        """Returns a parsed amount using app-wide preferences.

        This simply wraps :func:`core.model.amount.parse_amount` and adds default values.
        """
        if default_currency is None:
            default_currency = self._default_currency
        return parse_amount(amount, default_currency, auto_decimal_place=self._auto_decimal_place)

    def parse_date(self, date):
        """Returns a parsed date using app-wide preferences.

        This simply wraps :func:`core.model.date.parse_date` and adds default values.
        """
        return parse_date(date, self._date_format)

    def parse_search_query(self, query_string):
        """Parses ``query_string`` into something that can be used to filter transactions.

        :param str query_string: Search string that comes straight from the user through the search
                                 box.
        :rtype: a dict of query arguments
        """
        # Application might not be an appropriate place for this method. self._default_currency
        # is used, but I'm not even sure that it's appropriate to use it.
        query_string = query_string.strip().lower()
        ALL_QUERY_TYPES = ['account', 'group', 'amount', 'description', 'checkno', 'payee', 'memo']
        RE_TARGETED_SEARCH = re.compile(r'({}):(.*)'.format('|'.join(ALL_QUERY_TYPES)))
        m = RE_TARGETED_SEARCH.match(query_string)
        if m is not None:
            qtype, qargs = m.groups()
            qtypes = [qtype]
        else:
            qtypes = ALL_QUERY_TYPES
            qargs = query_string
        query = {}
        for qtype in qtypes:
            if qtype in {'account', 'group'}:
                # account and group args are comma-splitted
                query[qtype] = {s.strip() for s in qargs.split(',')}
            elif qtype == 'amount':
                try:
                    query['amount'] = abs(parse_amount(qargs, self._default_currency, with_expression=False))
                except ValueError:
                    pass
            else:
                query[qtype] = qargs
        return query

    def save_custom_range(self, slot, name, start, end):
        """Save a custom date range into our preferences.

        This will notify the UI to refresh the date range selector.

        :param int slot: The slot number (0-2) to save this range into.
        :param str name: A name for the range.
        :param datetime.date start: Start of the range.
        :param datetime.date end: End of the range.
        """
        self.saved_custom_ranges[slot] = SavedCustomRange(name, start, end)
        self._save_custom_ranges()

    def get_enabled_plugins(self):
        return [p for p in self.plugins if self.is_plugin_enabled(p)]

    def is_plugin_enabled(self, plugin):
        return plugin.is_core() and plugin.ENABLED_BY_DEFAULT

    def get_default(self, key, fallback_value=None):
        """Returns moneyGuru user pref for ``key``.

        .. seealso:: :meth:`ApplicationView.get_default`

        :param str key: The key of the prefence to return.
        :param fallback_value: if the pref doesn't exist or isn't of the same type as the
                               fallback value, return the fallback. Therefore, you can use the
                               fallback value as a way to tell "I expect preferences of this type".
        """
        result = nonone(self.view.get_default(key), fallback_value)
        if fallback_value is not None and not isinstance(result, type(fallback_value)):
            # we don't want to end up with garbage values from the prefs
            try:
                result = type(fallback_value)(result)
            except Exception:
                result = fallback_value
        return result

    def set_default(self, key, value):
        """Sets moneyGuru user pref to ``value`` for ``key``.

        .. seealso:: :meth:`ApplicationView.set_default`

        :param str key: The key of the prefence to set.
        :param value: The value to set the pref to.
        """
        self.view.set_default(key, value)

    @property
    def date_format(self):
        """Default, app-wide date format."""
        return self._date_format

    # --- Preferences
    @property
    def autosave_interval(self):
        """*get/set int*. Interval (in minutes) at which we perform autosave."""
        return self._autosave_interval

    @autosave_interval.setter
    def autosave_interval(self, value):
        if value == self._autosave_interval:
            return
        self._autosave_interval = value
        self.set_default(PreferenceNames.AutoSaveInterval, value)

    @property
    def auto_decimal_place(self):
        """*get/set bool*. Whether we automatically place decimal sep when parsing amounts.

        .. seealso:: :func:`core.model.amount.parse_amount`
        """
        return self._auto_decimal_place

    @auto_decimal_place.setter
    def auto_decimal_place(self, value):
        if value == self._auto_decimal_place:
            return
        self._auto_decimal_place = value
        self.set_default(PreferenceNames.AutoDecimalPlace, value)

    @property
    def day_first_date_entry(self):
        """*get/set bool*. Whether the user wants to enter dates in day -> month -> year order or
        the natural left-to-right order in the user's date format.
        """
        return self._day_first_date_entry

    @day_first_date_entry.setter
    def day_first_date_entry(self, value):
        if value == self._day_first_date_entry:
            return
        self._day_first_date_entry = value
        self.set_default(PreferenceNames.DayFirstDateEntry, value)
        self._update_date_entry_order()

    @property
    def show_schedule_scope_dialog(self):
        """*get/set bool*. Whether we prompt the user for schedule editing scope.

        When editing a schedule spawn, we need to know if the user intends this edit to be local or
        global. When this pref is true, we ask the user every time. When it's false, we always do
        local changes unless Shift is held.

        .. seealso:: :class:`core.model.recurrence.Recurrence`
        """
        return self._show_schedule_scope_dialog

    @show_schedule_scope_dialog.setter
    def show_schedule_scope_dialog(self, value):
        if value == self._show_schedule_scope_dialog:
            return
        self._show_schedule_scope_dialog = value
        self.set_default(PreferenceNames.ShowScheduleScopeDialog, value)

