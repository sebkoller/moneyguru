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

More responsibilities to the view classes
=========================================

With moneyGuru 2.0, a new view system is put in place. This will allow for new views to be more
easily added. In the *before times*, a lot of code that was specific to a view would go in the
:class:`.Document` because that was the only place it could go into. Shortly before the 2.0
refactoring, view classes were added, but they had very few responsibilities other than holding
references to their children. With 2.0, code is being pushed up to views to lighten up the
:class:`.Document` class which is getting pretty heavy.

Traditionally, all GUI elements were connected directly to the :class:`.Document` for notifications.
Since they were all independent from each other, it worked well. During the big 2.0 re-factoring,
more responsibilities were given to the view classes. Because most GUI elements are children to the
view classes (and thus not independent from them), the notification system caused problems because
in a lot of cases, when GUI would listen to the same notification as their view, the view needed to
process the notification first. Because no order is guaranteed in the notification dispatches, all
hell broke loose.

Most views only contain a handful of GUI elements. Therefore, moneyGuru's codebase is migrating to a
system where GUI elements that are part of views don't listen to :class:`.Document` notifications
anymore. The parent view takes the responsibility to call appropriate methods on their children when
it gets notifications from the :class:`.Document`.

It's rather ugly for now and results in code duplication in views' event handlers, but once the
re-factoring is over, some consolidation should be possible.
