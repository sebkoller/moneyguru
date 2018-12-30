========================
Understanding the source
========================

When looking at a non-trivial codebase for the first time, it's very difficult to understand
anything of it until you get the "Big Picture". This page is meant to, hopefully, make you get
moneyGuru's big picture.

UI agnostic
===========

moneyGuru used to have two UI codebases: one in Cocoa and one in Qt. Now that
moneyGuru is a GNU/Linux app, it doesn't matter much anymore, but much of its
design stems from this. We have a very strong separation between ``qt`` code
and ``core`` code.

Model/View/Controller
=====================

moneyGuru tries to follow the MVC pattern. The **View** layer is the platform dependent code
(Objective-C code and PyQt code). The role of that code is to be controlled by the **Controllers**,
which are located in the :mod:`core.gui` python package (which is platform independent). The role of
the controllers in :mod:`core.gui` is to "present" the data living in the **Model**
(:mod:`core.document` and :mod:`core.model`) to the user.

For example, :class:`.AccountPanel`, when its :meth:`.AccountPanel.load` method is called, checks
into its :class:`.Document` to see which :class:`.Account` instance is selected, then copies
relevant information from that :class:`.Account` instance into its ready-to-be-fetched-by-the-View
(on the Cocoa platform, the ``MGAccountProperties`` class) properties.

This method of having multiple GUI codebases is a little unusual. I call this "Cross-Toolkit
Software" and I've written `an article about it`_.

.. _writetoamodel:

core.document vs core.model
===========================

To ensure data integrity among model instances, all modifications to any model instance must take
place in the :class:`.Document`. For example, :attr:`.Transaction.description` must never be
directly set, because if it is, the :class:`.Document` will not be able to send proper notifications
to gui elements that the changes were made.

Therefore, the way :mod:`core.gui` instances work is that they happily dig directly into models to
fetch data, but when comes the time to change anything, they call the corresponding
:class:`.Document` method.

.. _cooking:

Raw data and Cooked data
========================

You might have noticed that unit with a funny name: :mod:`core.model.oven`. Its role is to "cook"
(compute) data from raw data. One example of such cooked data is the running balances (it's not
something that is saved in the moneyguru file, but it still has to be displayed by the views). Every
time that data changes (through the :class:`.Document`, of course), data has to be re-cooked by the
:class:`.Oven`.

Notification System
===================

There are lots of things that can trigger a change in the :mod:`core.gui` controllers, like data
change, date range change, file load, file import, etc.. These changes can very well not have been
initiated by the GUI controller that needs to be changed. This is why there's a notification system.
The way it works is that GUI controllers all listen to a :class:`.Broadcaster` (the only
broadcasters for now are :class:`.Document` and :class:`.ImportWindow`). When an event occurs in the
broadcaster, the message corresponding to that event is sent to all listeners (GUI controllers),
which then act accordingly (usually, they refresh their internal data representation, then tell
their own view, the platform-dependant one, to refresh). For example, when
:meth:`.EntryTable.save_edits` is called, :meth:`.Document.change_entry` is called as well, which
makes the :class:`.Document` broadcast ``transaction_changed``, which is then caught by the chart
(if it's visible), which will be refreshed.

Example
=======

Let's use a complete example. Let's see what happens in the code when you press on Show Info on an
account, change its name, then press Save. Follow this example through the code, or else you won't
understand crap.

When you press Show Info under Cocoa, ``editItemInfo:`` in ``MGMainWindow`` is called. This causes
the main window to call its core gui's :meth:`.MainWindow.edit_item`. Because we are currently in an
account view, :meth:`.AccountPanel.load` is called with the currently selected account as an
argument.

The :class:`.AccountPanel` loads information relative to that account in its own field (in
``_load()``). After that, ``post_load()`` (this is in ``core.gui.base.Panel``) is called on the view
so that it brings up all this information in the GUI.

When the ``NSTextField`` corresponding to the name is changed, nothing happens just yet. The new
name stays on the Cocoa side. However, when the Save button is clicked and
``MGAccountProperties.saveFields`` is called, the values of all the fields are sent to the
``[self py]`` proxy and then :meth:`.AccountPanel.save` is called.

This call then causes a call to :meth:`.Document.change_account`. This will assign the new values to
the :class:`.Account` instance, set a new undo point, re-cook data and broadcast an
``account_changed`` signal.

If you run a search for gui controllers that listen to the ``account_changed`` event, you'll see
that :class:`.Chart`, :class:`.ImportWindow` and :class:`.Report` listen to that event (by the way,
only controllers of visible views actually listen to events). :class:`.Chart` must be updated in
case the currency of the account changed. :class:`.ImportWindow` must update its list of account
targets. :class:`.Report` (net worth and profit & loss sheets) must be updated because they display
account information. If you look at what the :class:`.Report` does on ``account_changed``, you'll
see what most gui controllers do on most events::

    self.refresh()
    self.view.refresh()
    
The first line refreshes the controller's data representation (in this case, accounts organized in a
tree) and the second line tells the Cocoa view to refresh itself.

.. _an article about it: http://www.hardcoded.net/articles/cross-toolkit-software.htm
