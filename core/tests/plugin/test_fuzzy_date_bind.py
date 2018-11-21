# Copyright 2018 Virgil Dupras, Georg Drees
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

#
# TODO:
#       - higher level testing:
#           - verify weight recommendations lead to actually usable result
#

from datetime import date, timedelta
from itertools import starmap
from random import randint

from pytest import mark, raises

from hscommon.testutil import eq_

from ...model.amount import Amount
from ...model.entry import Entry
from ...model.transaction import Transaction
from ...plugin.fuzzy_date_bind import FuzzyDateBind

BASE_CONFIDENCE = FuzzyDateBind.BASE_CONFIDENCE
PENALTIES = FuzzyDateBind.PENALTIES


def create_entry(entry_date, description, amount):
    if isinstance(amount, Amount):
        txn = Transaction(entry_date, description=description, amount=amount)
    elif isinstance(amount, int) or isinstance(amount, float):
        txn = Transaction(entry_date, description=description, amount=Amount(amount, 'USD'))
    else:
        raise TypeError("amount must be of type model.amount.Amount, int or float!")
    if not isinstance(description, str):
        raise TypeError("description must be of type str!")
    split = txn.splits[0]
    return Entry(split, split.amount, 0, 0, 0)


def test_internal_create_entry_argument_fencing():
    # Verify that description and amount must be certain types
    # when created in tests.
    DATE = date(2017, 10, 10)
    create_entry(DATE, "string", Amount(42, 'USD'))
    create_entry(DATE, "string", 42)
    create_entry(DATE, "string", 4.20)
    with raises(TypeError):
        create_entry(DATE, "string", "33")
        create_entry(DATE, bytes("bad"), 42)


def test_single_imported_typical():
    # Verify that FuzzyDateBind.match_entries() returns weights modified
    # according to FuzzyDateBind.PENALTIES lookup and only if amounts match
    plugin = FuzzyDateBind()
    DATE = date(2017, 10, 10)
    existing_entries = list(starmap(create_entry, [
        (DATE, 'e1', 42),
        (DATE + timedelta(2), 'e2', 42),
        (DATE, 'e3 other amount', 11),
    ]))
    imported_entries = list(starmap(create_entry, [
        (DATE + timedelta(1), 'i1', 42),
    ]))
    matches = plugin.match_entries(None, None, None, existing_entries, imported_entries)
    EXPECTED = [('e1', 'i1', True, BASE_CONFIDENCE - PENALTIES[1]),
                ('e2', 'i1', True, BASE_CONFIDENCE - PENALTIES[-1])]
    result = [(m.existing.description, m.imported.description, m.will_import, m.weight) for m in matches]
    eq_(result, EXPECTED)


def test_outside_date_intervall():
    # Verify no matches are returned if all existing are not in date range
    plugin = FuzzyDateBind()
    DATE = date(2017, 10, 10)
    existing_entries = list(starmap(create_entry, [
        (DATE - FuzzyDateBind.DELTA_T - timedelta(1), 'e1out', 42),
        (DATE + FuzzyDateBind.DELTA_T + timedelta(1), 'e2out', 42),
    ]))
    imported_entries = list(starmap(create_entry, [
        (DATE, 'i1', 42),
    ]))
    matches = plugin.match_entries(None, None, None, existing_entries, imported_entries)
    result = [(m.existing.description, m.imported.description, m.will_import, m.weight) for m in matches]
    eq_(len(result), 0)


def test_match_for_each_existing_in_range():
    # Verify a match is created for each existing in the date range
    plugin = FuzzyDateBind()
    DATE = date(2017, 10, 10)
    for num in [0, 1, 2, randint(3, 50)]:  # TODO: Use fuzzer. Arbitrarily limited to limit the test runtime
        existing_entries = list(starmap(create_entry, [
            (DATE - FuzzyDateBind.DELTA_T - timedelta(1), 'e1out', 42),
            (DATE + FuzzyDateBind.DELTA_T + timedelta(1), 'e2out', 42),
        ]))
        for i in range(num):
            existing_entries.append(create_entry(DATE + timedelta(randint(-FuzzyDateBind.DELTA_T.days,
                                                                          +FuzzyDateBind.DELTA_T.days)),
                                                 'random entry',
                                                 42))
        imported_entries = list(starmap(create_entry, [
            (DATE, 'i1', 42),
        ]))
        matches = plugin.match_entries(None, None, None, existing_entries, imported_entries)
        result = [(m.existing.description, m.imported.description, m.will_import, m.weight) for m in matches]
        eq_(len(result), num)
        for r in result:
            eq_(r[0], 'random entry')
            eq_(r[1], 'i1')


@mark.xfail(reason="Python does not guarantee unix epoch safety, it depends on system C library.")
def test_unix_epoch():
    # Test using specific dates that could be problematic when the unix time
    # with 32 bit representation overflows. c.f. https://en.wikipedia.org/wiki/Unix_time
    # --> 03:14:08 UTC on Tuesday, 19 January 2038 for signed 32 bit
    # --> 06:28:15 UTC on Sunday, 7 February 2106 for unsigned 32 bit
    #
    # NOTE:
    # Currently python depends on your system's C library for date functionality
    # during unix epoch change to work correctly.
    eq_((date(2038, 1, 20) - date(2038, 1, 18)).days, 2)
    eq_((date(2038, 1, 18) - date(2038, 1, 20)).days, -2)
    eq_((date(2106, 2, 8) - date(2106, 2, 6)).days, 2)
    eq_((date(2106, 2, 6) - date(2106, 2, 8)).days, -2)
