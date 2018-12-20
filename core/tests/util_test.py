# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .testutil import eq_
from ..util import (
    nonone, tryint, minmax, first, flatten, dedupe, stripfalse, extract,
    allsame, escape, remove_invalid_xml
)

def test_nonone():
    eq_('foo', nonone('foo', 'bar'))
    eq_('bar', nonone(None, 'bar'))

def test_tryint():
    eq_(42,tryint('42'))
    eq_(0,tryint('abc'))
    eq_(0,tryint(None))
    eq_(42,tryint(None, 42))

def test_minmax():
    eq_(minmax(2, 1, 3), 2)
    eq_(minmax(0, 1, 3), 1)
    eq_(minmax(4, 1, 3), 3)

#--- Sequence

def test_first():
    eq_(first([3, 2, 1]), 3)
    eq_(first(i for i in [3, 2, 1] if i < 3), 2)

def test_flatten():
    eq_([1,2,3,4],flatten([[1,2],[3,4]]))
    eq_([],flatten([]))

def test_dedupe():
    reflist = [0,7,1,2,3,4,4,5,6,7,1,2,3]
    eq_(dedupe(reflist),[0,7,1,2,3,4,5,6])

def test_stripfalse():
    eq_([1, 2, 3], stripfalse([None, 0, 1, 2, 3, None]))

def test_extract():
    wheat, shaft = extract(lambda n: n % 2 == 0, list(range(10)))
    eq_(wheat, [0, 2, 4, 6, 8])
    eq_(shaft, [1, 3, 5, 7, 9])

def test_allsame():
    assert allsame([42, 42, 42])
    assert not allsame([42, 43, 42])
    assert not allsame([43, 42, 42])
    # Works on non-sequence as well
    assert allsame(iter([42, 42, 42]))

#--- String

def test_escape():
    eq_('f\\o\\ob\\ar', escape('foobar', 'oa'))
    eq_('f*o*ob*ar', escape('foobar', 'oa', '*'))
    eq_('f*o*ob*ar', escape('foobar', set('oa'), '*'))

def test_remove_invalid_xml():
    eq_(remove_invalid_xml('foo\0bar\x0bbaz'), 'foo bar baz')
    # surrogate blocks have to be replaced, but not the rest
    eq_(remove_invalid_xml('foo\ud800bar\udfffbaz\ue000'), 'foo bar baz\ue000')
    # replace with something else
    eq_(remove_invalid_xml('foo\0baz', replace_with='bar'), 'foobarbaz')

