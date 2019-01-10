# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtWidgets import QWidget

class BaseView(QWidget):
    def __init__(self, model, mainwindow):
        QWidget.__init__(self)
        # Needed for CSS selectors targeting names to work
        self.setObjectName(self.__class__.__name__)
        self.model = model
        self.mainwindow = mainwindow
        self._setup()
        # self.model.view usually triggers calls that require the view's children to be set up.
        self.model.view = self

    def _setup(self):
        raise NotImplementedError()

    def fitViewsForPrint(self, viewPrinter):
        viewPrinter.fit(self, 42, 42, expandH=True, expandV=True)

    def restoreSubviewsSize(self):
        # This is called by the main window just after the base view has been added to the widget
        # stack. This means that its size has just been adjusted and now is the time to restore,
        # if needed, the sizes of the subviews. It is also called by the model callback
        # restore_subviews_size() which happens when a document is loaded.
        pass

    # --- model --> view
    def restore_subviews_size(self):
        self.restoreSubviewsSize()
