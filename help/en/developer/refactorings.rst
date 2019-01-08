====================
Ongoing Refactorings
====================

Some big refactorings take time. This is the page where the currently ongoing refactoring are listed so that you aren't surprised to see lack of consistency in these areas.

ccore vs core
=============

``ccore`` is a newcomer, there used to be only ``core`` with a small
``_amount`` C module to speed up amount calculations. Now, ``ccore`` is slowly
eating ``core``'s lunch because moneyGuru's author is getting a bit tired with
Python and wants to learn C more.

So, what is ``ccore``? The "very core" of moneyGuru's models, written in C. In
it, a ``py_ccore.c`` unit that is a Python C module to interface this pure C
code with Python. This unit can grow very big, very fast (at this time, it's
already a monolithic 3500 lines unit) and it doesn't split well in multiple
units. The ongoing Python-to-C conversion is made in a way that minimizes the
size of this unit by trying to make pure C structures and functions opaque to
Python as fast as possible (if Python doesn't need to see them, no need to
interface them).

Eventually, ``core`` won't exist anymore and all we'll have is ``ccore`` with
a Python test suite. We'll also keep ``qt`` intact, but I'm thinking about a
possible new ``ncurses`` C UI code base to go alongside it.
