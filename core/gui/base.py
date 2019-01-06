# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .print_view import PrintView

def noop(*args, **kwargs):
    pass

class NoopGUI:
    def __getattr__(self, func_name):
        return noop

class GUIObject:
    """Cross-toolkit "model" representation of a GUI layer object.

    A ``GUIObject`` is a cross-toolkit "model" representation of a GUI layer object, for example, a
    table. It acts as a cross-toolkit interface to what we call here a :attr:`view`. That
    view is a toolkit-specific controller to the actual view (an ``NSTableView``, a ``QTableView``,
    etc.). In our GUIObject, we need a reference to that toolkit-specific controller because some
    actions have effects on it (for example, prompting it to refresh its data). The ``GUIObject``
    is typically instantiated before its :attr:`view`, that is why we set it to ``None`` on init.
    However, the GUI layer is supposed to set the view as soon as its toolkit-specific controller is
    instantiated.

    When you subclass ``GUIObject``, you will likely want to update its view on instantiation. That
    is why we call ``self.view.refresh()`` in :meth:`_view_updated`. If you need another type of
    action on view instantiation, just override the method.

    Most of the time, you will only one to bind a view once in the lifetime of your GUI object.
    That is why there are safeguards, when setting ``view`` to ensure that we don't double-assign.
    However, sometimes you want to be able to re-bind another view. In this case, set the
    ``multibind`` flag to ``True`` and the safeguard will be disabled.
    """
    def __init__(self, multibind=False):
        self._view = None
        self._multibind = multibind

    def _view_updated(self):
        """(Virtual) Called after :attr:`view` has been set.

        Doing nothing by default, this method is called after :attr:`view` has been set (it isn't
        called when it's unset, however). Use this for initialization code that requires a view
        (which is often the whole of the initialization code).
        """

    def has_view(self):
        return (self._view is not None) and (not isinstance(self._view, NoopGUI))

    @property
    def view(self):
        """A reference to our toolkit-specific view controller.

        *view answering to GUIObject sublass's view protocol*. *get/set*

        This view starts as ``None`` and has to be set "manually". There's two times at which we set
        the view property: On initialization, where we set the view that we'll use for our lifetime,
        and just before the view is deallocated. We need to unset our view at that time to avoid
        calls to a deallocated instance (which means a crash).

        To unset our view, we simple assign it to ``None``.
        """
        return self._view

    @view.setter
    def view(self, value):
        if self._view is None and value is None:
            # Initial view assignment
            return
        if self._view is None or self._multibind:
            if value is None:
                value = NoopGUI()
            self._view = value
            self._view_updated()
        else:
            assert value is None
            # Instead of None, we put a NoopGUI() there to avoid rogue view callback raising an
            # exception.
            self._view = NoopGUI()


class ViewChild(GUIObject):
    def __init__(self, parent_view):
        GUIObject.__init__(self)
        self.parent_view = parent_view
        self.mainwindow = parent_view.mainwindow
        self.document = self.mainwindow.document
        self.app = self.document.app

    def _revalidate(self):
        """*Virtual*. Refresh the GUI element's content.

        Override this when you subclass with code that refreshes the content of the element. This is
        called when we show the element back and that we had received a notification invalidating
        our content.
        """

    def restore_view(self):
        """ Called when the view needs to restore it's state from preferences.
        """


class GUIPanel(GUIObject):
    """GUI Modal dialog.

    All panels work pretty much the same way: They load up an object's
    properties, let the user fiddle with them, and then save those properties
    back in the object.

    As :ref:`described in the devdoc overview <writetoamodel>`, saving to an
    object doesn't mean directly doing so. We need to go through the
    :class:`.Document` to do that. Therefore, :meth:`save` doesn't actually do
    that job, but merely calls the proper document method, with the proper
    arguments.

    Subclasses :class:`.GUIObject`.
    """
    def __init__(self, mainwindow):
        super().__init__()
        self.mainwindow = mainwindow
        #: Parent :class:`document <.Document>`.
        self.document = mainwindow.document
        #: Parent :class:`app <.Application>`.
        self.app = self.document.app

    # --- Virtual
    def _load(self):
        """*Virtual*. Load the panel's content.

        The subclass is supposed to know what it has to load from the document (selected
        transaction, selected account, etc.). That's where it does this.
        """
        raise NotImplementedError()

    def _new(self):
        """*Virtual*. Load the panel's content with default values for creation.

        We're creating a new element with our panel. Load it with appropriate initialization values.
        """
        raise NotImplementedError()

    def _save(self):
        """*Virtual*. Save the panel's value into the document.

        Our user confirmed the dialog, thus triggering a save operation. Commit our panel's content
        into our document.
        """
        raise NotImplementedError()

    # --- Overrides
    def load(self, *args, **kwargs):
        """Load the panel's content.

        This :meth:`load operation <_load>` is wrapped in between ``pre_load()`` and ``post_load()``
        calls to the panel's view.

        If you pass arguments to this method, they will be directly passed to :meth:`_load`, thus
        allowing your panel subclasses to take arbitrary arguments.

        If the panel can't load, :exc:`.OperationAborted` will be raised. If a message to the user
        is required, the :exc:`.OperationAborted` exception will have a non-empty message.
        """
        self.view.pre_load()
        self._load(*args, **kwargs)
        self.view.post_load()

    def new(self):
        """Load the panel's content with default values for creation.

        Same as :meth:`load` but with new values.
        """
        self.view.pre_load()
        self._new()
        self.view.post_load()

    def save(self):
        """Save the panel's value into the document.

        This :meth:`save operation <_save>` is preceded by a ``pre_save()`` call to the panel's
        view.
        """
        self.view.pre_save()
        self._save()


class DocumentGUIObject(GUIObject):
    def __init__(self, document):
        super().__init__()
        self.document = document
        self.app = document.app
        self._doc_step = 0

    def invalidate(self):
        self._doc_step = 0

    def revalidate(self):
        if self.document.step > self._doc_step:
            self._revalidate()
            self._doc_step = self.document.step


class BaseView(DocumentGUIObject):
    """ The next generation of BaseView.

    Unlike BaseView, it doesn't listen or repeat document notifications at all. It's based on the
    new, simpler mtime-based refresh system.

    The goal is to completely replace BaseView before the next release (which will probably be
    v3.0).
    """
    # --- model -> view calls:
    # restore_subviews_size()
    #

    #: A :class:`.PaneType` constant uniquely identifying our subclass.
    VIEW_TYPE = -1
    #: The class to use as a model when printing a tab. Defaults to :class:`.PrintView`.
    PRINT_VIEW_CLASS = PrintView

    def __init__(self, mainwindow):
        super().__init__(mainwindow.document)
        self.mainwindow = mainwindow
        self.document = mainwindow.document
        self._status_line = ""

    # --- Temporary stubs
    def show(self):
        self.revalidate()

    def hide(self):
        pass

    # --- Virtual
    def apply_date_range(self, new_date_range, prev_date_range):
        """A new date range was just set. Adapt to it."""

    def apply_filter(self):
        """A new filter was just applied. Adapt to it."""

    def new_item(self):
        """*Virtual*. Create a new item."""
        raise NotImplementedError()

    def edit_item(self):
        """*Virtual*. Edit the selected item(s)."""
        raise NotImplementedError()

    def delete_item(self):
        """*Virtual*. Delete the selected item(s)."""
        raise NotImplementedError()

    def duplicate_item(self):
        """*Virtual*. Duplicate the selected item(s)."""
        raise NotImplementedError()

    def new_group(self):
        """*Virtual*. Create a new group."""
        raise NotImplementedError()

    def navigate_back(self):
        """*Virtual*. Navigate back from wherever the user is coming.

        This may (will) result in the active tab changing.
        """
        raise NotImplementedError()

    def move_up(self):
        """*Virtual*. Move select item(s) up in the list, if possible."""
        raise NotImplementedError()

    def move_down(self):
        """*Virtual*. Move select item(s) down in the list, if possible."""
        raise NotImplementedError()

    def restore_view(self):
        """ Restore view (recursively) param from preferences."""

    def stop_editing(self):
        """If we're editing something, stop now."""

    def update_transaction_selection(self, transactions):
        """Transactions were just selected."""

    def update_visibility(self):
        """One of the main window's main part had its visibility toggled."""

    # --- Private
    def _revalidate(self):
        pass

    # --- Public
    @classmethod
    def can_perform(cls, action_name):
        """Returns whether our view subclass can perform ``action_name``.

        Base views have a specific set of actions they can perform, and the way they perform these
        actions is defined by the subclasses. However, not all views can perform all actions.
        You can use this method to determine whether a view can perform an action. It does so by
        comparing the method of the view with our base method which we know is abstract and if
        it's not the same, we know that the method was overridden and that we can perform the
        action.
        """
        mymethod = getattr(cls, action_name, None)
        assert mymethod is not None
        return mymethod is not getattr(BaseView, action_name, None)

    def restore_subviews_size(self):
        """*Virtual*. Restore subviews size from preferences."""

    def save_preferences(self):
        """*Virtual*. Save subviews size to preferences."""

    # --- Properties
    @property
    def status_line(self):
        """*get/set*. A short textual description of the global status of the tab.

        This is displayed at the bottom of the main window in the UI.
        """
        return self._status_line

    @status_line.setter
    def status_line(self, value):
        self._status_line = value
        self.mainwindow.update_status_line()
