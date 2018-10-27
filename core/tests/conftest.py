# Copyright 2017 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# This unit is required to make tests work with py.test. When running

import os
import time
import pytest
import logging

from hscommon.testutil import pytest_funcarg__app # noqa

from ..model.currency import RatesDB, Currency
from ..model import currency as currency_module

logging.basicConfig(level=logging.DEBUG)

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
        Currency.set_rates_db(ratesdb)

    global global_monkeypatch
    monkeypatch = config.pluginmanager.getplugin('monkeypatch')
    global_monkeypatch = monkeypatch.monkeypatch()
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

def pytest_unconfigure(config):
    global global_monkeypatch
    global_monkeypatch.undo()

def pytest_funcarg__monkeypatch(request):
    monkeyplus = request.getfuncargvalue('monkeyplus')
    return monkeyplus

