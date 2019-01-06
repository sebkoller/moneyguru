# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# This unit is required to make tests work with py.test. When running

import os
import time
import pytest
import logging
import datetime

from .testutil import app # noqa
from _pytest.monkeypatch import MonkeyPatch

from ..model.currency import RatesDB, Currencies
from ..model import currency as currency_module

logging.basicConfig(level=logging.DEBUG)

@pytest.fixture
def monkeyplus(request):
    result = _monkeyplus()
    request.addfinalizer(result.undo)
    return result

class _monkeyplus(MonkeyPatch):
    def patch_today(self, year, month, day):
        """Patches today's date to date(year, month, day)
        """
        # For the patching to work system wide, time.time() must be patched. However, there is no way
        # to get a time.time() value out of a datetime, so a timedelta must be used
        new_today = datetime.date(year, month, day)
        today = datetime.date.today()
        time_now = time.time()
        delta = today - new_today
        self.setattr(time, 'time', lambda: time_now - (delta.days * 24 * 60 * 60))
        from core.model._ccore import patch_today
        patch_today(new_today)

    def patch_time_ticking(self, force_int_diff=False):
        """Patches time.time() and ensures that it never returns the same value each time it's
        called.

        If force_int_diff is True, the minimum difference between time() result is 1.
        """
        if hasattr(self, '_time_before_ticking_patch'):
            # Already patched, do nothing.
            return
        self._last_time_tick = time.time()
        if force_int_diff:
            self._last_time_tick = int(self._last_time_tick)
        self._time_before_ticking_patch = time.time

        def fake_time():
            result = self._time_before_ticking_patch()
            if force_int_diff:
                result = int(result)
            if result <= self._last_time_tick:
                result = self._last_time_tick + 1
            self._last_time_tick = result
            return result

        self.setattr(time, 'time', fake_time)

    def undo(self):
        super().undo()
        from core.model._ccore import patch_today
        patch_today(None)


global_monkeypatch = None

def pytest_addoption(parser):
    parser.addoption(
        "--run-network", action="store_true",
        default=False, help="run tests that need network"
    )

def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-network"):
        # --run-network given in cli: do not skip slow tests
        return
    skip_network = pytest.mark.skip(reason="need --run-network option to run")
    for item in items:
        if "needs_network" in item.keywords:
            item.add_marker(skip_network)

def pytest_configure(config):
    def fake_initialize_db(path):
        ratesdb = RatesDB(':memory:', async_=False)
        ratesdb.register_rate_provider = lambda *a: None
        Currencies.set_rates_db(ratesdb)

    import faulthandler
    faulthandler.enable()
    global global_monkeypatch
    monkeypatch = config.pluginmanager.getplugin('monkeypatch')
    global_monkeypatch = monkeypatch.MonkeyPatch()
    # The vast majority of moneyGuru's tests require that ensure_rates is patched to nothing to
    # avoid hitting the currency server during tests. However, some tests still need it. This is
    # why we keep it around so that those tests can re-patch it.
    global_monkeypatch.setattr(currency_module, 'initialize_db', fake_initialize_db)
    # Avoid false test failures caused by timezones messing up our date fakeries.
    # See http://stackoverflow.com/questions/9915058/pythons-fromtimestamp-does-a-discrete-jump
    os.environ['TZ'] = 'UTC'
    try:
        time.tzset()
    except AttributeError:
        # We're on Windows. Oh, well...
        pass

    from . import base
    tmpdir = config.pluginmanager.getplugin('tmpdir')
    tmp_path_factory = tmpdir.TempPathFactory.from_config(config)
    base._global_tmpdir = tmp_path_factory.mktemp('mgtest')


def pytest_unconfigure(config):
    global global_monkeypatch
    global_monkeypatch.undo()

@pytest.fixture
def monkeypatch(request):
    monkeyplus = request.getfixturevalue('monkeyplus')
    return monkeyplus

