# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from datetime import date
from itertools import starmap

from hscommon.testutil import eq_

from ...model.amount import Amount
from ...model.entry import Entry
from ...model.transaction import Transaction
from ...plugin.base_import_bind import ReferenceBind

def create_entry(entry_date, description, reference):
    txn = Transaction(entry_date, description=description, amount=Amount(1, 'USD'))
    split = txn.splits[0]
    split.reference = reference
    return Entry(split, txn, split.amount, 0, 0, 0)

def test_typical_situation():
    # Verify that ReferenceBind.match_entries() return expected entried in a typical situation
    # We only match entries with the same reference
    plugin = ReferenceBind()
    DATE = date(2017, 10, 10)
    existing_entries = list(starmap(create_entry, [
        (DATE, 'e1', 'ref1'),
        (DATE, 'e2', 'ref2'),
    ]))
    imported_entries = list(starmap(create_entry, [
        (DATE, 'i1', 'ref1'),
        (DATE, 'i2', 'ref3'),
    ]))
    matches = plugin.match_entries(None, None, None, existing_entries, imported_entries)
    EXPECTED = [('e1', 'i1', True, 0.99)]
    result = [(m.existing.description, m.imported.description, m.will_import, m.weight) for m in matches]
    eq_(result, EXPECTED)

def test_reconciled_entry():
    # Reconciled entries are matched, but with will_import = False
    plugin = ReferenceBind()
    DATE = date(2017, 10, 10)
    existing = create_entry(DATE, 'e1', 'ref1')
    existing.split.reconciliation_date = DATE
    imported = create_entry(DATE, 'i1', 'ref1')
    matches = plugin.match_entries(None, None, None, [existing], [imported])
    EXPECTED = [('e1', 'i1', False, 0.99)]
    result = [(m.existing.description, m.imported.description, m.will_import, m.weight) for m in matches]
    eq_(result, EXPECTED)

def test_match_first_only():
    # If two entries have the same reference, we only get one match (we don't care which, it's not
    # really supposed to happen...).
    # Verify that ReferenceBind.match_entries() return expected entried in a typical situation
    # We only match entries with the same reference
    plugin = ReferenceBind()
    DATE = date(2017, 10, 10)
    existing_entries = list(starmap(create_entry, [
        (DATE, 'e1', 'ref1'),
    ]))
    imported_entries = list(starmap(create_entry, [
        (DATE, 'i1', 'ref1'),
        (DATE, 'i2', 'ref1'),
    ]))
    matches = plugin.match_entries(None, None, None, existing_entries, imported_entries)
    eq_(len(matches), 1)

