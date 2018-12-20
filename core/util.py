# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import sys
import os
import os.path as op
import re
from datetime import timedelta

def nonone(value, replace_value):
    """Returns ``value`` if ``value`` is not ``None``. Returns ``replace_value`` otherwise.
    """
    if value is None:
        return replace_value
    else:
        return value

def tryint(value, default=0):
    """Tries to convert ``value`` to in ``int`` and returns ``default`` if it fails.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

def minmax(value, min_value, max_value):
    """Returns `value` or one of the min/max bounds if `value` is not between them.
    """
    return min(max(value, min_value), max_value)

# --- Sequence related

def dedupe(iterable):
    """Returns a list of elements in ``iterable`` with all dupes removed.

    The order of the elements is preserved.
    """
    result = []
    seen = {}
    for item in iterable:
        if item in seen:
            continue
        seen[item] = 1
        result.append(item)
    return result

def flatten(iterables, start_with=None):
    """Takes a list of lists ``iterables`` and returns a list containing elements of every list.

    If ``start_with`` is not ``None``, the result will start with ``start_with`` items, exactly as
    if ``start_with`` would be the first item of lists.
    """
    result = []
    if start_with:
        result.extend(start_with)
    for iterable in iterables:
        result.extend(iterable)
    return result

def first(iterable):
    """Returns the first item of ``iterable``.
    """
    try:
        return next(iter(iterable))
    except StopIteration:
        return None

def stripfalse(seq):
    """Returns a sequence with all false elements stripped out of seq.
    """
    return [x for x in seq if x]

def extract(predicate, iterable):
    """Separates the wheat from the shaft (`predicate` defines what's the wheat), and returns both.
    """
    wheat = []
    shaft = []
    for item in iterable:
        if predicate(item):
            wheat.append(item)
        else:
            shaft.append(item)
    return wheat, shaft

def allsame(iterable):
    """Returns whether all elements of 'iterable' are the same.
    """
    it = iter(iterable)
    try:
        first_item = next(it)
    except StopIteration:
        raise ValueError("iterable cannot be empty")
    return all(element == first_item for element in it)

# --- String related

def escape(s, to_escape, escape_with='\\'):
    """Returns ``s`` with characters in ``to_escape`` all prepended with ``escape_with``.
    """
    return ''.join((escape_with + c if c in to_escape else c) for c in s)

_valid_xml_range = '\x09\x0A\x0D\x20-\uD7FF\uE000-\uFFFD'
if sys.maxunicode > 0x10000:
    _valid_xml_range += '%s-%s' % (chr(0x10000), chr(min(sys.maxunicode, 0x10FFFF)))
RE_INVALID_XML_SUB = re.compile('[^%s]' % _valid_xml_range, re.U).sub

def remove_invalid_xml(s, replace_with=' '):
    return RE_INVALID_XML_SUB(replace_with, s)

# --- Date related

# It might seem like needless namespace pollution, but the speedup gained by this constant is
# significant, so it stays.
ONE_DAY = timedelta(1)
def iterdaterange(start, end):
    """Yields every day between ``start`` and ``end``.
    """
    date = start
    while date <= end:
        yield date
        date += ONE_DAY

# --- Files related

def ensure_folder(path):
    "Create `path` as a folder if it doesn't exist."
    if not op.exists(path):
        os.makedirs(path)

