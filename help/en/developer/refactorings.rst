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

De-notification
===============

The Document notification system is there to ensure that all GUI elements are
properly refreshed when the document is changed. In retrospective, I find this
system overly complicated. While it allows a fine level of granularity in the
type of updates that we perform (so that we can theoretically refresh "just
what we need" instead of performing a full refresh), in practice this isn't
used and full refreshes on most notifications are the norm.

I want to simplify this by scrapping all notifications and replace them with a
"modification marker". Every time the document is modified, this marker is
incremented. Base views then keep track of the markers value whenever they
refresh. When the base view is shown, it checks whether it needs to refresh
itself by comparing its modification marker with the document's.

When a view is the actor of a change (and therefore the active view), it knows
what it does, so it can possibly bypass this system and perform more granular
refresh operations when it makes sense.

There are some special notifications related to date range and filter bar
changes. I don't know yet the implications of the refactoring for those
notifications, but I suppose a similar and separate marker could be added for
those two and used by relevant views.

In short: let's simplify the view refresh system at the cost of a coarser
granularity.
