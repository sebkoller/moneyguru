# Created On: 2012/02/02
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

"""API to create moneyGuru plugins.

This module was designed to allow developers to easily create plugins for moneyGuru. moneyGuru being
open source, we can already add anything anywhere, but the bar of entry for doing so can be high.

The goal here is to lower the bar of entry by having a simple API to do simple things. Many of the
classes below are either base classes or helper classes. If you want to develop a plugin, this is
the list of classes you can subclass:

* :class:`ReadOnlyTablePlugin`
* :class:`CurrencyProviderPlugin`
"""

from datetime import date


from collections import namedtuple

from core.notify import Broadcaster
from ..model.currency import Currencies, CurrencyNotSupportedException
from ..gui.base import BaseView
from ..gui.table import GUITable, Row
from ..const import PaneType

class Plugin:
    """Base class for all plugins.

    By itself, it doesn't do much except offer common attributes to all plugins. Don't subclass
    this directly.
    """
    #: Display name of the plugin (for when we list plugins and stuff)
    NAME = ''
    #: Display name of the plugin basic type (import action, currency, etc.)
    TYPE_NAME = ''
    #: Author of the plugin
    AUTHOR = ''
    #: Determines the loading order of the plugins. Lower priorities are loaded first.
    PRIORITY = 0
    #: Whether this plugin is a View, and thus should be in the plugin section of the New View tab.
    IS_VIEW = False
    #: Whether the plugin is enabled by default. Only works with core plugins
    ENABLED_BY_DEFAULT = False

    @classmethod
    def plugin_id(cls):
        return "{}.{}".format(cls.__module__, cls.__qualname__)

    @classmethod
    def is_core(cls):
        return cls.plugin_id().startswith('core.')


class ViewPlugin(Plugin):
    """Base class for viewable plugins.

    Once again, we don't subclass this directly. The way viewable plugin work is that the base
    system provides a couple of view "templates" to offer to the plugin developer, who is then able
    to fill the template with data within that template's bounds.

    This system is there to simplify the plugin developer's work, because otherwise he would have
    to manually code the Qt and Cocoa layers for each view plugin, which could get complicated.

    Subclasses :class:`.Plugin`.
    """
    IS_VIEW = True

    def __init__(self, mainwindow):
        #: The plugin's parent :class:`.MainWindow`.
        self.mainwindow = mainwindow
        #: The plugin's parent :class:`.Document`.
        self.document = mainwindow.document

class ReadOnlyTableRow(Row):
    """A :class:`.Row` with a simplified API for plugin developers."""
    def set_field(self, name, value, sort_value=None):
        """Set the value of an arbitrary field name in the row.

        :param str name: Name of the field to set.
        :param str value: Display value of the field.
        :param sort_value: Value to use for sorting.
        """
        setattr(self, name, value)
        if sort_value is not None:
            setattr(self, '_'+name, sort_value)


class ReadOnlyTable(GUITable):
    """A read-only table to be used in a :class:`.ViewPlugin`.

    It fetches its ``COLUMNS`` attribute (see :class:`.Columns`) directly from its parent plugin
    so that we don't have to subclass this table simply for defining columns.

    Subclasses :class:`.GUITable`.
    """
    def __init__(self, plugin):
        #: The parent plugin.
        self.plugin = plugin
        self.COLUMNS = plugin.COLUMNS
        GUITable.__init__(self, plugin.document)

    def _fill(self):
        self.plugin.fill_table()


class ReadOnlyTableView(BaseView):
    """View for :class:`.ReadOnlyTablePlugin`.

    A simple view containing a :class:`.ReadOnlyTable`, used by :class:`.ReadOnlyTablePlugin`.

    Subclasses :class:`.BaseView`.
    """
    VIEW_TYPE = PaneType.ReadOnlyTablePlugin

    def __init__(self, plugin):
        BaseView.__init__(self, plugin.mainwindow)
        self.plugin = plugin
        self.table = ReadOnlyTable(plugin)
        self.bind_messages(self.INVALIDATING_MESSAGES, self._revalidate)

    def _revalidate(self):
        self.table.refresh_and_show_selection()


class ReadOnlyTablePlugin(ViewPlugin):
    """A view plugin that contains a read-only table.

    To create a plugin from this, subclass it, fill :attr:`COLUMNS` and implement
    :meth:`fill_table`.

    Subclasses :class:`ViewPlugin`.
    """
    TYPE_NAME = "Display Table"
    #: List of columns to be displayed in our table. See :class:`Columns`.
    COLUMNS = []

    def __init__(self, mainwindow):
        ViewPlugin.__init__(self, mainwindow)
        #: Instance of :class:`ReadOnlyTableView`
        self.view = ReadOnlyTableView(self)
        #: Instance of :class:`ReadOnlyTable`
        self.table = self.view.table

    def add_row(self):
        """Add a row to our table and return it.

        :rtype: :class:`ReadOnlyTableRow`
        """
        row = ReadOnlyTableRow(self.table)
        self.table.append(row)
        return row

    def fill_table(self):
        """Fills our table with its intended contents.

        Subclass this to add content to your table. The principle is rather simple: Add your rows
        with :meth:`add_row` and call :meth:`ReadOnlyTableRow.set_field` to set the contents of each
        row.
        """
        raise NotImplementedError()

class CurrencyProviderPlugin(Plugin):
    """Plugin allowing the creation of new currencies and the fetching of their rates.

    By subclassing this plugin, you can add new currencies to moneyGuru and also add a new source
    to fetch those currencies' exchange rates.

    Subclasses :class:`Plugin`
    """
    TYPE_NAME = "Currency Provider"

    def __init__(self):
        Plugin.__init__(self)
        self.supported_currency_codes = set()
        try:
            for code, name, exponent, fallback_rate in self.register_currencies():
                self.register_currency(code, name, exponent=exponent, latest_rate=fallback_rate)
        except TypeError: # We return None, which means we registered all currencies manually.
            pass
        Currencies.sort_currencies()

    def wrapped_get_currency_rates(self, currency_code, start_date, end_date):
        """Tries to fetch exchange rates for ``currency_code``.

        If our currency is supported by our plugin, we first try the "simple" fetching
        (:meth:`get_currency_rate_today`). If it's not implemented, we try the "complex" one
        (:meth:`get_currency_rates`). We return the result of the first method to work.

        If we can't get results, either because our currency isn't supported or because our
        implementation is incomplete, :exc:`.CurrencyNotSupportedException` is raised.

        This method isn't designed to be overriden.
        """
        if currency_code not in self.supported_currency_codes:
            raise CurrencyNotSupportedException()
        try:
            simple_result = self.get_currency_rate_today(currency_code)
            if simple_result is not None:
                return [(date.today(), simple_result)]
            else:
                return []
        except NotImplementedError:
            try:
                return self.get_currency_rates(currency_code, start_date, end_date)
            except NotImplementedError:
                raise CurrencyNotSupportedException()

    def register_currency(self, code, name, **kwargs):
        """Register a currency.

        Calling this gives more options than the simple return scheme of :meth:`register_currencies`.

        ``**kwargs`` is passed directly to :meth:`Currency.register`.

        Returns the resulting currency instance.
        """
        result = Currencies.register(code, name, **kwargs)
        self.supported_currency_codes.add(code)
        return result

    def register_currencies(self):
        """Override this and return a list of new currencies to support.

        The expected return value is a list of tuples ``(code, name, exponent, fallback_rate)``.

        If you need to set more option, call :meth:`register_currency` instead.

        ``exponent`` is the number of decimal numbers that should be displayed when formatting
        amounts in this currency.

        ``fallback_rate`` is the rate to use in case we can't fetch a rate. You can use the rate
        that is in effect when you write the plugin. Of course, it will become wildly innaccurate
        over time, but it's still better than a rate of ``1``.
        """
        raise NotImplementedError()

    def get_currency_rate_today(self, currency_code):
        """Override this if you have a 'simple' provider.

        If your provider doesn't give rates for any other date than today, overriding this method
        instead of get_currency_rate() is the simplest choice.

        ``currency_code`` is a string representing the code of the currency to fetch, 'USD' for
        example.

        Return a float representing the value of 1 unit of your currency in CAD.

        If you can't get a rate, return ``None``.

        This method is called asynchronously, so it won't block moneyGuru if it takes time to
        resolve.
        """
        raise NotImplementedError()

    def get_currency_rates(self, currency_code, start_date, end_date):
        """Override this if your provider gives rates for past dates.

        If your provider gives rates for past dates, it's better (although a bit more complicated)
        to override this method so that moneyGuru can have more accurate rates.

        You must return a list of tuples (date, rate) with all rates you can fetch between
        start_date and end_date. You don't need to have one item for every single date in the range
        (for example, most of the time we don't have values during week-ends), moneyGuru correctly
        handles holes in those values. Simply return whatever you can get.

        If you can't get a rate, return an empty list.

        This method is called asynchronously, so it won't block moneyGuru if it takes time to
        resolve.
        """
        raise NotImplementedError()

class ImportActionPlugin(Plugin, Broadcaster):
    """
    Plugin allowing certain kinds of actions to be performed on import.
    By subclassing this plugin, you can add new currencies to moneyGuru and also add a new source
    to fetch those currencies' exchange rates.
    Subclasses :class:`Plugin`, :class:`Broadcaster`
    """
    TYPE_NAME = "Import Action"

    # Signal to the import window to change the name in our drop down list
    action_name_changed = 'action_name_changed'

    # The name that appears in our drop down list
    ACTION_NAME = None

    def __init__(self):
        Plugin.__init__(self)
        Broadcaster.__init__(self)

    def on_selected_pane_changed(self, selected_pane):
        """This method is called whenever the import window has changed it's selected pane."""
        pass

    def always_perform_action(self):
        return False

    def can_perform_action(self, import_document, transactions, panes, selected_rows=None):
        return True

    def perform_action(self, import_document, transactions, panes, selected_rows=None):
        pass


EntryMatch = namedtuple('EntryMatch', 'existing imported will_import weight')


class ImportBindPlugin(Plugin):
    TYPE_NAME = "Import Bind"

    def match_entries(self, target_account, document, import_document, existing_entries, imported_entries):
        # Returns a list of EntryMatch objects.
        return []

