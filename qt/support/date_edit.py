# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import Qt, QTimer

from .search_edit import ClearableEdit
from core.gui.date_widget import DateWidget

class DateEdit(ClearableEdit):
    KEY2METHOD = {
        Qt.Key_Left: 'left',
        Qt.Key_Right: 'right',
        Qt.Key_Up: 'increase',
        Qt.Key_Down: 'decrease',
        Qt.Key_Backspace: 'backspace',
        Qt.Key_Delete: 'backspace',
    }
    ACCEPTED_KEYS = {Qt.Key_Escape, Qt.Key_Tab, Qt.Key_Backtab, Qt.Key_Return, Qt.Key_Enter}
    DATE_FORMAT = 'dd/MM/yyyy'

    def __init__(self, parent, is_clearable=False):
        self.widget = DateWidget(self.DATE_FORMAT)
        self.widget.text = ''
        ClearableEdit.__init__(self, parent, is_clearable=is_clearable)

    def _refresh(self):
        self.setText(self.widget.text)
        selStart, selEnd = self.widget.selection
        self.setSelection(selStart, selEnd-selStart+1)

    # --- Overrides
    def _clearSearch(self):
        self.widget.date = None
        self._refresh()

    def _hasClearableContent(self):
        return self.widget.date is not None

    def keyPressEvent(self, event):
        key = event.key()
        if key in self.KEY2METHOD:
            getattr(self.widget, self.KEY2METHOD[key])()
            self._refresh()
        elif key in self.ACCEPTED_KEYS:
            # We want keypresses like Escape to go through.
            ClearableEdit.keyPressEvent(self, event)
        else:
            text = str(event.text())
            if text in "0123456789/-.":
                self.widget.type(text)
                self._refresh()

    def focusInEvent(self, event):
        ClearableEdit.focusInEvent(self, event)
        self.widget.text = str(self.text())
        # A timer is used here because a mouse event following the focusInEvent messes up the
        # selection (so the refresh *has* to happen after the mouse event).
        QTimer.singleShot(0, self._refresh)

    def focusOutEvent(self, event):
        self.prepareDataForCommit()
        ClearableEdit.focusOutEvent(self, event)

    def setText(self, value):
        self.widget.text = value
        super().setText(value)

    # --- Public
    def prepareDataForCommit(self):
        self.widget.exit()
        self._refresh()

