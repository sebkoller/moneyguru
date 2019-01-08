# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..const import PaneType
from .base import BaseView

class EmptyView(BaseView):
    VIEW_TYPE = PaneType.Empty

    # --- Public
    def select_pane_type(self, pane_type):
        self.mainwindow.set_current_pane_type(pane_type)
