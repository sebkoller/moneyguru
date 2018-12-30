# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# Column is not used in this unit, but is imported to allow plugins to easily be able to import it.
from ..gui.column import Column # noqa

from .api import ( # noqa
    Plugin, ViewPlugin, ReadOnlyTableRow, ReadOnlyTable, ReadOnlyTableView, ReadOnlyTablePlugin,
    CurrencyProviderPlugin, ImportActionPlugin, ImportBindPlugin, EntryMatch
)

def get_plugins_from_mod(mod):
    result = []
    for x in vars(mod).values():
        try:
            if issubclass(x, Plugin) and x.NAME:
                result.append(x)
        except TypeError: # not a class, we don't care and ignore
            pass
    return sorted(result, key=lambda x: x.PRIORITY)

def get_all_core_plugin_modules():
    from . import (
        account_list, currency_rates, payee_breakdown, boc_currency_provider,
        stale_currency_provider,
        base_import_actions, base_import_bind,
        fuzzy_date_bind,
    )
    return [
        account_list,
        currency_rates,
        payee_breakdown,
        boc_currency_provider,
        stale_currency_provider,
        base_import_actions,
        base_import_bind,
        fuzzy_date_bind,
    ]

