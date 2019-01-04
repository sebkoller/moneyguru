# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from .text_field import TextField

class SearchField(TextField):
    def __init__(self, mainwindow):
        TextField.__init__(self)
        self.mainwindow = mainwindow

    def _update(self, newvalue):
        self.mainwindow.filter_string = newvalue

    def refresh(self):
        self._text = self._value = self.mainwindow.filter_string
        self.view.refresh()

