# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from collections import defaultdict
from itertools import combinations

from core.util import extract

from ..model.sort import sort_string
from .base import NoopGUI

def has_letters(s, query):
    s_letters = defaultdict(int)
    query_letters = defaultdict(int)
    for letter in query:
        query_letters[letter] += 1
    for letter in s:
        s_letters[letter] += 1
    for letter, count in query_letters.items():
        if s_letters[letter] < count:
            return False
    return True

def letter_distance(s, letter1, letter2):
    indexes1 = [i for i, l in enumerate(s) if l == letter1]
    indexes2 = [i for i, l in enumerate(s) if l == letter2]
    return min(abs(i-j) for i in indexes1 for j in indexes2 if i != j)

def letters_distance(s, query):
    return sum(letter_distance(s, l1, l2) for l1, l2 in combinations(query, 2))

class Lookup:
    """Fuzzily-filtered list of items that match the few letters that the user typed.

    A Lookup allows the user to quickly find a object he looks for by name by typing only a few
    letters from that name. When first invoked, we start with a list of all possible items, and as
    letters are typed, those items and filtered *and* ordered in a way that fuzzily matches what
    our user typed.

    The list's filter is very inclusive and will include object that very remotely can match user's
    input, but the order is based on what matches the most.

    For example, if the user types "ab", the lookup list would contain both "barber", "absolute",
    and "albinos" (all those names contain both "a" and "b"), but would be ordered so that
    "absolute" comes first because it's the closest match.

    Pressing Return will "activate" (see :meth:`go`) the first item in the list, but the user can
    also navigate the list with the arrow keys (or click on the wanted item), which is why we keep
    track of :attr:`selected_index`.

    This class is designed to be subclassed with concrete named objects to lookup in. It does
    nothing by itself.
    """
    def __init__(self, mainwindow):
        #: :class:`.MainWindow`
        self.mainwindow = mainwindow
        #: :class:`.Document`
        self.document = mainwindow.document
        self._original_names = []
        self._filtered_names = []
        self._search_query = ''
        #: *int*. Currently selected index in the filtered/ordered list.
        self.selected_index = 0
        self.view = NoopGUI()

    def _apply_query(self):
        # On top, we want exact matches (the name starts with the query). Then, we want matches
        # that contain all the letters, sorted in order of names that have query letters as close
        # to each other as possible.
        q = sort_string(self._search_query)
        matches1, rest = extract(lambda n: n.startswith(q), self._original_names)
        matches2, rest = extract(lambda n: q in n, rest)
        matches3, rest = extract(lambda n: has_letters(n, q), rest)
        matches3.sort(key=lambda n: letters_distance(n, q))
        self._filtered_names = matches1 + matches2 + matches3
        self.selected_index = max(self.selected_index, 0)
        self.selected_index = min(self.selected_index, len(self._filtered_names)-1)

    def _generate_lookup_names(self):
        """*Virtual*. Return a list of names in which we'll search."""
        return []

    def _go(self, name):
        """*Virtual*. Select an item named ``name``.

        The nature of this action depends on what kind of object we perform the lookup on. Were
        those accounts? Then open up the account named ``name``.
        """

    def _refresh(self):
        self._search_query = ''
        self.selected_index = 0
        names = self._generate_lookup_names()
        normalized_names = [sort_string(n) for n in names]
        self._normalized2original = {}
        for normalized, original in zip(normalized_names, names):
            self._normalized2original[normalized] = original
        self._original_names = normalized_names
        self._filtered_names = normalized_names

    def go(self):
        """Activate the :attr:`selected item <selected_index>` and close the lookup.

        To "activate", we call :meth:`_go` with the name of our selected item.
        """
        try:
            name = self.names[self.selected_index]
            self._go(name)
        except IndexError:
            pass # No result, do nothing
        self.view.hide()

    def show(self):
        """Refreshes the name list and show the lookup."""
        self._refresh()
        self.view.refresh()
        self.view.show()

    # --- Properties
    @property
    def names(self):
        """List of filtered/ordered names based on :attr:`search_query`."""
        return [self._normalized2original[n] for n in self._filtered_names]

    @property
    def search_query(self):
        """*get/set*. *str*. Search query typed by the user."""
        return self._search_query

    @search_query.setter
    def search_query(self, value):
        if value == self._search_query:
            return
        self._search_query = value
        self._apply_query()
        self.view.refresh()

