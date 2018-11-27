# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtCore import QObject

class FilterBar(QObject):
    BUTTONS = [] # (Title, FilterID)

    def __init__(self, model, view):
        # the view is a support.RadioBox
        QObject.__init__(self, None)
        self.model = model
        self.view = view
        self.view.items = [title for title, _ in self.BUTTONS]
        self.model.view = self

        self.view.itemSelected.connect(self.itemSelected)

    # --- Event Handlers
    def itemSelected(self, index):
        _, filterId = self.BUTTONS[index]
        self.model.filter_type = filterId

    # --- model --> view
    def refresh(self):
        for index, (title, filterId) in enumerate(self.BUTTONS):
            if filterId is self.model.filter_type:
                self.view.selected_index = index
                break

