# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os.path as op
from datetime import date
from operator import attrgetter

from ..app import Application, PreferenceNames
from ..document import Document, ScheduleScope
from ..exception import FileFormatError
from ..const import PaneType
from ..gui.base import GUIObject
from ..gui.completable_edit import CompletableEdit
from ..gui.main_window import MainWindow
from ..gui.account_panel import AccountPanel
from ..loader import base
from ..model.account import AccountType, ACCOUNT_SORT_KEY
from ..model.amount import parse_amount
from ..model.date import DateFormat
from ..util import flatten
from .testutil import eq_, CallLogger, TestApp as TestAppBase, TestData
from .testutil import with_app # noqa

testdata = TestData(op.join(op.dirname(__file__), 'testdata'))

# is set in conftest.py
_global_tmpdir = None

class PanelViewProvider:
    """Provide dummy views for panels during tests.

    Also, keep track of the last panel invoked. This is pretty much the only way to manage
    to reach those panels because their instance are not referenced anywhere in the app
    (they are shown and then discarded right away).
    """
    def __init__(self):
        self.current_panel = None

    def close_panel(self):
        self.current_panel = None

    @classmethod
    def _logify(cls, model, ignore=None):
        ignore = ignore or []
        for elem in vars(model).values():
            if elem is model or elem in ignore:
                continue
            if isinstance(elem, GUIObject) and elem.view is None:
                elem.view = CallLogger()
                cls._logify(elem, ignore + [model])

    def get_panel_view(self, model):
        self._logify(model)
        self.current_panel = model
        # We have to hold onto this instance for a while
        self.current_panel_view = CallLogger()
        return self.current_panel_view


def log(method):
    def wrapper(self, *args, **kw):
        result = method(self, *args, **kw)
        self.calls.append(method.__name__)
        return result

    return wrapper

class ApplicationGUI(CallLogger):
    def __init__(self):
        CallLogger.__init__(self)
        # We don't want the autosave thread to mess up with testunits
        self.defaults = {PreferenceNames.AutoSaveInterval: 0}

    def get_default(self, key): # We don't want to log this one. It disturbs other test and is pointless to log
        return self.defaults.get(key)

    @log
    def set_default(self, key, value):
        self.defaults[key] = value


class DocumentGUI(CallLogger):
    def __init__(self):
        CallLogger.__init__(self)
        self.query_for_schedule_scope_result = ScheduleScope.Local

    @log
    def query_for_schedule_scope(self):
        return self.query_for_schedule_scope_result


class ViewGUI(CallLogger):
    def __init__(self, panel_view_provider):
        CallLogger.__init__(self)
        self.panel_view_provider = panel_view_provider

    @log
    def get_panel_view(self, model):
        return self.panel_view_provider.get_panel_view(model)

class MainWindowGUI(CallLogger):
    def __init__(self, testapp):
        CallLogger.__init__(self)
        self.messages = []
        self.testapp = testapp

    @log
    def get_panel_view(self, model):
        return self.testapp.panel_view_provider.get_panel_view(model)

    @log
    def show_message(self, message):
        self.messages.append(message)

    # Link the view of lazily loaded elements.
    @log
    def refresh_panes(self):
        app = self.testapp
        for i in range(app.mw.pane_count):
            app.link_gui(
                app.mw.pane_view(i),
                ViewGUI(self.testapp.panel_view_provider)
            )

class DictLoader(base.Loader):
    """Used for fake_import"""
    def __init__(
            self, default_currency, infos, default_date_format='%d/%m/%Y'):
        # `infos` look like:
        # [{'name': 'account name',
        #   'reference': ...,
        #   'txns': [{'date': ..., 'description': ...}]
        # }]
        base.Loader.__init__(self, default_currency, default_date_format)
        self.infos = infos
        alltxns = flatten(info['txns'] for info in infos)
        str_dates = [txn['date'] for txn in alltxns]
        self.parsing_date_format = self.guess_date_format(str_dates)

    def _parse(self, infile):
        pass

    def _load(self):
        for info in self.infos:
            self.account_info.name = info['name']
            self.account_info.reference = info.get('reference')
            for txn in info['txns']:
                self.start_transaction()
                for attr, value in txn.items():
                    if attr == 'date':
                        value = self.parse_date_str(value)
                    setattr(self.transaction_info, attr, value)
            self.flush_account()

class TestApp(TestAppBase):
    __test__ = False
    def __init__(self, app=None, doc=None, appargs=None):
        TestAppBase.__init__(self)
        self.panel_view_provider = PanelViewProvider()
        link_gui = self.link_gui
        if app is None:
            if not appargs:
                appargs = {}
            app = Application(self.make_logger(ApplicationGUI()), **appargs)
        app.autosave_interval = 0
        self.app = app
        self.app_gui = app.view
        if doc is None:
            doc = Document(self.app)
            doc.view = self.make_logger(DocumentGUI())
        self.doc = doc
        self.doc_gui = doc.view
        self.mainwindow = MainWindow(self.doc)
        # we set mainwindow's view at the end because it triggers daterangeselector refreshes
        # which needs to have its own view set first.
        # XXX The way our GUI instances are created in TestApp is incompatible with the lazy view
        # creation path that moneyGuru is engaged in. Changing all tests is way too big a task,
        # but we can at least make new tests comply with lazy view creation. Ideally, all these
        # "nwview", "ttable" and others wouldn't exist in TestApp, we'd get a view instance by the
        # return value of TestApp.show_*view() and access its child GUI objects through that
        # reference.
        self.mw = self.mainwindow # shortcut. This one is often typed
        self.default_parent = self.mw
        self.sfield = link_gui(self.mw.search_field)
        self.drsel = link_gui(self.mw.daterange_selector)
        self.alookup = link_gui(self.mw.account_lookup)
        self.clookup = link_gui(self.mw.completion_lookup)
        self.mw.view = self.make_logger(MainWindowGUI(self))
        self.mainwindow_gui = self.mw.view

    def link_gui(self, gui, logger=None):
        if gui.view is None:
            gui.view = self.make_logger(logger=logger)
        # link sub GUIs too
        for elem in vars(gui).values():
            if elem is gui or elem is self.mw:
                continue
            if isinstance(elem, GUIObject) and elem.view is None:
                self.link_gui(elem)
        return gui

    def tmppath(self):
        assert _global_tmpdir is not None
        return str(_global_tmpdir)

    def check_current_pane(self, pane_type, account_name=None):
        """Asserts that the currently selecte pane in the main window is of the specified type and,
        optionally, shows the correct account.
        """
        index = self.mw.current_pane_index
        eq_(self.mw.pane_type(index), pane_type)
        if account_name is not None:
            # This method is a little flimsy (testing account name through pane label), but it works
            # for now.
            eq_(self.mw.pane_label(index), account_name)

    @staticmethod
    def check_gui_calls(gui, *args, **kwargs):
        gui.check_gui_calls(*args, **kwargs)

    @staticmethod
    def check_gui_calls_partial(gui, *args, **kwargs):
        gui.check_gui_calls_partial(*args, **kwargs)

    def add_account(
            self, name=None, currency=None, account_type=AccountType.Asset, group_name=None,
            account_number=None, inactive=None):
        # This method simulates what a user would do to add an account with the specified attributes
        # Note that, undo-wise, this operation is not atomic.
        if account_type in (AccountType.Income, AccountType.Expense):
            self.show_pview()
            sheet = self.istatement
            if account_type == AccountType.Income:
                sheet.selected = sheet.income
            else:
                sheet.selected = sheet.expenses
        else:
            self.show_nwview()
            sheet = self.bsheet
            if account_type == AccountType.Asset:
                sheet.selected = sheet.assets
            else:
                sheet.selected = sheet.liabilities
        if group_name:
            predicate = lambda n: n.name == group_name
            group_node = sheet.find(predicate, include_self=False)
            if group_node:
                sheet.selected = group_node
        self.mw.new_item()
        if currency or account_number or inactive:
            self.change_selected_account(
                name=name, currency=currency, account_number=account_number, inactive=inactive
            )
        elif name is not None:
            sheet.selected.name = name
            sheet.save_edits()

    def add_accounts(self, *names):
        # add a serie of simple accounts, *names being names for each account
        for name in names:
            self.add_account(name)

    def add_budget(
            self, account_name, str_amount, start_date=None,
            repeat_type_index=2, repeat_every=1, stop_date=None):
        # if no target, set target_name to None
        self.show_bview()
        bpanel = self.mainwindow.new_item()
        if start_date is None:
            start_date = self.app.format_date(date(date.today().year, date.today().month, 1))
        bpanel.start_date = start_date
        bpanel.repeat_type_list.select(repeat_type_index)
        bpanel.repeat_every = repeat_every
        if stop_date is not None:
            bpanel.stop_date = stop_date
        account_index = bpanel.account_list.index(account_name)
        bpanel.account_list.select(account_index)
        bpanel.amount = str_amount
        bpanel.save()

    def add_entry(self, date=None, description=None, payee=None, transfer=None, increase=None,
            decrease=None, checkno=None, reconciliation_date=None):
        # This whole "if not None" thing allows to simulate a user tabbing over fields leaving the
        # default value.
        self.etable.add()
        row = self.etable.edited
        if date is not None:
            row.date = date
        if description is not None:
            row.description = description
        if payee is not None:
            row.payee = payee
        if transfer is not None:
            row.transfer = transfer
        if increase is not None:
            row.increase = increase
        if decrease is not None:
            row.decrease = decrease
        if checkno is not None:
            row.checkno = checkno
        if reconciliation_date is not None:
            row.reconciliation_date = reconciliation_date
        self.etable.save_edits()

    def add_group(self, name=None, account_type=AccountType.Asset):
        group = self.doc.new_group(account_type)
        if name is not None:
            self.doc.change_group(group, name=name)
        self.mw.revalidate()

    def add_schedule(self, start_date=None, description='', account=None, amount='0',
            repeat_type_index=0, repeat_every=1, stop_date=None):
        if start_date is None:
            start_date = self.app.format_date(date(date.today().year, date.today().month, 1))
        scview = self.show_scview()
        scpanel = scview.new_item()
        scpanel.start_date = start_date
        scpanel.description = description
        scpanel.repeat_type_list.select(repeat_type_index)
        scpanel.repeat_every = repeat_every
        if stop_date is not None:
            scpanel.stop_date = stop_date
        if account:
            scpanel.split_table.add()
            scpanel.split_table.edited.account = account
            if self.doc.parse_amount(amount) >= 0:
                scpanel.split_table.edited.debit = amount
            else:
                scpanel.split_table.edited.credit = amount
            scpanel.split_table.save_edits()
        scpanel.save()

    def add_txn(self, date=None, description=None, payee=None, from_=None, to=None, amount=None,
            checkno=None):
        self.show_tview()
        self.ttable.add()
        row = self.ttable.edited
        if date is not None:
            row.date = date
        if description is not None:
            row.description = description
        if payee is not None:
            row.payee = payee
        if from_ is not None:
            row.from_ = from_
        if to is not None:
            row.to = to
        if amount is not None:
            row.amount = amount
        if checkno is not None:
            row.checkno = checkno
        self.ttable.save_edits()

    def add_txn_with_splits(self, splits, date=None, description=None, payee=None, checkno=None):
        # If splits is not None, additional splits will be added to the txn. The format of the
        # splits argument is [(account_name, memo, debit, credit)]. Don't forget that if they don't
        # balance, you end up with an imbalance split.
        self.add_txn(date=date, description=description, payee=payee, checkno=checkno)
        tpanel = self.mw.edit_item()
        stable = tpanel.split_table
        for index, (account, memo, debit, credit) in enumerate(splits):
            if index >= len(stable):
                stable.add()
            row = stable[index]
            row.account = account
            row.memo = memo
            row.debit = debit
            row.credit = credit
            stable.save_edits()
        tpanel.save()

    def account_names(self):
        accounts = list(self.doc.accounts)
        accounts.sort(key=ACCOUNT_SORT_KEY)
        return [a.name for a in accounts]

    def account_node_subaccount_count(self, node):
        # In the balance sheet and the income statement testing for emptyness becomes cumbersome
        # because of the 2 total nodes (1 total, 1 blank) that are always there, even if empty. To
        # avoid putting a comment next to each len() test, just use this method.
        return len(node) - 2

    def balances(self):
        return [self.etable[i].balance for i in range(len(self.etable))]

    def bar_graph_data(self):
        result = []
        xoffset = self.bargraph._xoffset
        for x1, x2, y1, y2 in self.bargraph.data:
            # We have to account for the padding...
            padding = (x2 - x1) / 3
            x1 = int(round(x1 - padding))
            x2 = int(round(x2 + padding))
            convert = lambda i: date.fromordinal(i+xoffset).strftime('%d/%m/%Y')
            result.append((convert(x1), convert(x2), '%2.2f' % y1, '%2.2f' % y2))
        return result

    def close_and_load(self):
        self.mw.close()
        app = Application(self.app_gui)
        doc = Document(self.app)
        doc.view = self.doc_gui
        return TestApp(app=app, doc=doc)

    def change_selected_account(
            self, name=None, currency=None, account_type=None, account_number=None, inactive=None):
        assert account_type is None, "account_type not supported yet, add support now!"
        apanel = self.mw.edit_item()
        assert isinstance(apanel, AccountPanel)
        if name:
            apanel.name = name
        if currency:
            apanel.currency = currency
        if account_number:
            apanel.account_number = account_number
        if inactive is not None:
            apanel.inactive = inactive
        apanel.save()

    def completable_edit(self, attrname):
        ce = CompletableEdit(self.mw)
        ce.view = self.make_logger()
        ce.attrname = attrname
        return ce

    def do_test_save_load(self):
        newapp = self.save_and_load()
        newapp.drsel.set_date_range(self.doc.date_range)
        newapp.doc._cook()
        compare_apps(self.doc, newapp.doc)

    def do_test_qif_export_import(self):
        filepath = op.join(self.tmppath(), 'foo.qif')
        self.mainwindow.export()
        expanel = self.get_current_panel()
        expanel.export_path = filepath
        expanel.save()
        newapp = Application(ApplicationGUI(), default_currency=self.doc.default_currency)
        app = TestApp(app=newapp)
        try:
            iwin = app.mw.parse_file_for_import(filepath)
            while iwin.panes:
                iwin.import_selected_pane()
        except FileFormatError:
            pass
        compare_apps(self.doc, app.doc, qif_mode=True)

    def entry_descriptions(self):
        return [self.etable[i].description for i in range(len(self.etable))]

    def etable_count(self):
        # Now that the entry table has a total row, it messes up all tests that check the length
        # of etable. Rather than having confusing expected numbers with a comment explaining why we
        # add one to the expected count, we use this method that subtract 1 to the len of etable.
        return len(self.etable) - 1

    def fake_import(self, account_name, transactions, account_reference=None):
        # When you want to test the post-parsing import process, rather than going through the hoops,
        # use this methods. 'transactions' is a list of dicts, the dicts being attribute values.
        # dates are strings in the app's default date format.
        default_date_format = DateFormat(self.app.date_format).sys_format
        infos = [{
            'name': account_name,
            'reference': account_reference,
            'txns': transactions,
        }]
        self.mw.loader = DictLoader(
            self.doc.default_currency, infos,
            default_date_format=default_date_format
        )
        return self.mw.load_parsed_file_for_import()

    def get_current_panel(self):
        """Returns the instance of the last invoked panel.
        """
        return self.panel_view_provider.current_panel

    def graph_data(self):
        xoffset = self.balgraph._xoffset
        convert = lambda i: date.fromordinal(i+xoffset).strftime('%d/%m/%Y')
        return [(convert(x), '%2.2f' % y) for x, y in self.balgraph.data]

    def navigate_to_date(self, year, month, day):
        # navigate the current date range until target_date is in it. We use year month day to avoid
        # having to import datetime.date in tests.
        assert self.doc.date_range.can_navigate
        self.drsel.set_date_range(self.doc.date_range.around(date(year, month, day)))

    def new_app_same_prefs(self):
        # Returns a new TestApp() but with the same app_gui as before, thus preserving preferences.
        app = Application(self.app_gui)
        return TestApp(app=app)

    def nw_graph_data(self):
        xoffset = self.nwgraph._xoffset
        convert = lambda i: date.fromordinal(i+xoffset).strftime('%d/%m/%Y')
        return [(convert(x), '%2.2f' % y) for x, y in self.nwgraph.data]

    def save_and_load(self):
        # saves the current document and returns a new app with that document loaded
        filepath = op.join(self.tmppath(), 'foo.xml')
        self.mw.save_to_xml(str(filepath))
        self.mw.close()
        newapp = TestApp(app=self.app)
        newapp.mw.load_from_xml(str(filepath))
        return newapp

    def save_file(self):
        filename = op.join(self.tmppath(), 'foo.xml')
        self.mw.save_to_xml(filename) # reset the dirty flag
        return filename

    def select_account(self, account_name):
        # Selects the account with `account_name` in the appropriate sheet
        predicate = lambda node: getattr(node, 'is_account', False) and node.name == account_name
        self.show_nwview()
        node = self.bsheet.find(predicate)
        if node is not None:
            self.bsheet.selected = node
            return
        self.show_pview()
        node = self.istatement.find(predicate)
        if node is not None:
            self.istatement.selected = node
            return
        else:
            raise LookupError("Trying to show an account that doesn't exist")

    def show_account(self, account_name=None):
        # Selects the account with `account_name` in the appropriate sheet and calls show_selected_account()
        # If account_name is None, we simply show the currently selected account.
        if account_name:
            self.select_account(account_name)
        self.mw.show_account()
        self.link_aview()
        return self.current_view()

    def set_column_visible(self, colname, visible):
        # Toggling column from the UI is rather simple for a human, but not for a program. The
        # column menu is filled with display names and colname is an identifier.
        assert self.mw._current_pane.view.columns is not None
        items = self.mw.column_menu_items()
        if colname == 'debit_credit':
            # This is a special one
            display = "Debit/Credit"
        else:
            display = self.mw._current_pane.view.columns.column_display(colname)
        itemdisplays = [item[0] for item in items]
        assert display in itemdisplays
        index = itemdisplays.index(display)
        # Now that we have our index, just toggle the menu item if the marked flag isn't what our
        # visible flag is.
        marked = items[index][1]
        if marked != visible:
            self.mw.toggle_column_menu_item(index)

    def transaction_descriptions(self):
        return [row.description for row in self.ttable.rows]

    def set_plugins(self, plugins):
        # Changes the list of currently active plugins in `self.app` to `plugins`.
        class bag: pass
        fakemod = bag()
        for index, plugin in enumerate(plugins):
            setattr(fakemod, 'plugin%d' % index, plugin)
            plugin.ENABLED_BY_DEFAULT = True
        self.app.plugins = []
        self.app._load_plugin_module(fakemod)
        self.app._hook_currency_providers()

    # --- Shortcut for selecting a view type.
    def current_view(self):
        return self.mw.pane_view(self.mw.current_pane_index)

    def new_tab(self):
        self.mw.new_tab()
        return self.current_view()

    def link_aview(self):
        # Unlike other views, we constantly overwrite our aview-based GUI's here because we have
        # one view per opened account, but many legacy tests were designed with one account view in
        # mind. link_aview() allows us to easily adapt legacy code, but future tests should stop
        # using app.etable/app.balgraph/etc. and work directly with the return result of
        # app.show_account(), which is an AccountView instance.
        assert self.current_view().VIEW_TYPE == PaneType.Account
        self.aview = self.link_gui(self.current_view())
        self.etable = self.link_gui(self.aview.etable)
        self.etable_gui = self.etable.view
        self.balgraph = self.link_gui(self.aview.balgraph)
        self.balgraph_gui = self.balgraph.view
        self.bargraph = self.link_gui(self.aview.bargraph)
        self.bargraph_gui = self.bargraph.view
        self.efbar = self.link_gui(self.aview.filter_bar)

    def show_nwview(self):
        self.mw.select_pane_of_type(PaneType.NetWorth)
        if not hasattr(self, 'nwview'):
            self.nwview = self.link_gui(self.current_view())
            self.nwgraph = self.link_gui(self.nwview.nwgraph)
            self.nwgraph_gui = self.nwgraph.view
            self.bsheet = self.link_gui(self.nwview.bsheet)
            self.bsheet_gui = self.bsheet.view
        return self.current_view()

    def show_pview(self):
        self.mw.select_pane_of_type(PaneType.Profit)
        if not hasattr(self, 'pview'):
            self.pview = self.link_gui(self.current_view())
            self.pgraph = self.link_gui(self.pview.pgraph)
            self.istatement = self.link_gui(self.pview.istatement)
            self.istatement_gui = self.istatement.view
        return self.current_view()

    def show_tview(self):
        self.mw.select_pane_of_type(PaneType.Transaction)
        if not hasattr(self, 'tview'):
            self.tview = self.link_gui(self.current_view())
            self.ttable = self.link_gui(self.tview.ttable)
            self.ttable_gui = self.ttable.view
            self.tfbar = self.link_gui(self.tview.filter_bar)
        return self.current_view()

    def show_aview(self):
        # We don do GUI linking here because that method cannot be called unless the pane has
        # already been brought up by a specific account-opening method. Call link_aview()
        self.mw.select_pane_of_type(PaneType.Account)
        return self.current_view()

    def show_bview(self):
        self.mw.select_pane_of_type(PaneType.Budget)
        if not hasattr(self, 'bview'):
            self.bview = self.current_view()
            self.btable = self.link_gui(self.bview.table)
        return self.current_view()

    def show_scview(self):
        self.mw.select_pane_of_type(PaneType.Schedule)
        if not hasattr(self, 'scview'):
            self.scview = self.link_gui(self.current_view())
            self.sctable = self.link_gui(self.scview.table)
        return self.current_view()

    def show_glview(self):
        self.mw.select_pane_of_type(PaneType.GeneralLedger)
        if not hasattr(self, 'glview'):
            self.glview = self.link_gui(self.current_view())
            self.gltable = self.link_gui(self.glview.gltable)
        return self.current_view()

    def show_dpview(self):
        self.mw.select_pane_of_type(PaneType.DocProps)
        return self.current_view()


def compare_apps(first, second, qif_mode=False):
    def compare_txns(txn1, txn2):
        try: # XXX Why is there a try/except here? To catch silently some exeptions?
            eq_(txn1.date, txn2.date)
            eq_(txn1.description, txn2.description)
            eq_(txn1.payee, txn2.payee)
            eq_(txn1.checkno, txn2.checkno)
            if not qif_mode:
                eq_(txn1.notes, txn2.notes)
            eq_(len(txn1.splits), len(txn2.splits))
        except AssertionError:
            raise
        splits1 = txn1.splits
        splits2 = txn2.splits
        splits1.sort(key=lambda s: getattr(s.account, 'name', ''))
        splits2.sort(key=lambda s: getattr(s.account, 'name', ''))
        for split1, split2 in zip(splits1, splits2):
            try:
                account1 = split1.account.name if split1.account else ''
                account2 = split2.account.name if split2.account else ''
                eq_(account1, account2)
                if qif_mode:
                    eq_(split1.amount, split2.amount)
                else:
                    eq_(split1.memo, split2.memo)
                    eq_(split1.amount, split2.amount)
                eq_(split1.reconciled, split2.reconciled)
            except AssertionError:
                raise

    eq_(len(first.groups), len(second.groups))
    group_pairs = list(zip(sorted(first.groups, key=attrgetter('name')),
        sorted(second.groups, key=attrgetter('name'))))
    for group1, group2 in group_pairs:
        try:
            eq_(group1.name, group2.name)
            eq_(group1.type, group2.type)
        except AssertionError:
            raise
    eq_(len(first.accounts), len(second.accounts))
    account_pairs = list(zip(sorted(first.accounts, key=attrgetter('name')),
        sorted(second.accounts, key=attrgetter('name'))))
    for account1, account2 in account_pairs:
        try:
            eq_(account1.name, account2.name)
            eq_(account1.type, account2.type)
            if not qif_mode:
                for attr in ['currency', 'account_number', 'inactive', 'notes']:
                    eq_(getattr(account1, attr), getattr(account2, attr))
            if hasattr(first, 'entrycounts'):
                # We have a doc copy created in undo_test
                expected_count = first.entrycounts[account1.name]
            else:
                entries = first.accounts.entries_for_account(account1)
                expected_count = len(entries)
            entries = second.accounts.entries_for_account(account2)
            eq_(expected_count, len(entries))
        except AssertionError:
            raise
    eq_(len(first.transactions), len(second.transactions))
    for txn1, txn2 in zip(first.transactions, second.transactions):
        compare_txns(txn1, txn2)
    eq_(len(first.schedules), len(second.schedules))
    for rec1, rec2 in zip(first.schedules, second.schedules):
        eq_(rec1.repeat_type, rec2.repeat_type)
        eq_(rec1.repeat_every, rec2.repeat_every)
        compare_txns(rec1.ref, rec2.ref)
        eq_(rec1.stop_date, rec2.stop_date)
        eq_(len(rec1.date2exception), len(rec2.date2exception))
        for date_ in rec1.date2exception:
            exc1 = rec1.date2exception[date_]
            exc2 = rec2.date2exception[date_]
            if exc1 is None:
                assert exc2 is None
            else:
                compare_txns(exc1, exc2)
        eq_(len(rec1.date2globalchange), len(rec2.date2globalchange))
        for date_ in rec1.date2globalchange:
            txn1 = rec1.date2globalchange[date_]
            txn2 = rec2.date2globalchange[date_]
            compare_txns(txn1, txn2)
    for budget1, budget2 in zip(first.budgets, second.budgets):
        eq_(budget1.account.name, budget2.account.name)
        eq_(budget1.amount, budget2.amount)
        eq_(budget1.notes, budget2.notes)
        eq_(budget1.repeat_type, budget2.repeat_type)
        eq_(budget1.start_date, budget2.start_date)
        eq_(budget1.stop_date, budget2.stop_date)
        eq_(budget1.repeat_every, budget2.repeat_every)

def print_table(table, extra_attrs=[]):
    def getval(row, attrname):
        try:
            return str(row.get_cell_value(attrname))
        except AttributeError:
            return 'N/A'

    attrs = table.columns.colnames + extra_attrs
    print('|'.join(attrs))
    for row in table:
        print('|'.join(getval(row, attrname) for attrname in attrs))
    print("--- Row Count: {} ---".format(len(table)))

# Amount used to to be a Python class and was used at a lot of places. With the
# conversion to C, amount creation ended up being pretty much exclusive to the
# C core, which makes us want to remove the Python initializer for the Amount
# class. Amount initializer was still widely used in tests, however and for
# that purpose, this adapter was created.
def Amount(val, currency):
    return parse_amount('{} {}'.format(val, currency))
