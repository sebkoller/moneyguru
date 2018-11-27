# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..support.text_field import TextField

class SearchField(TextField):
    def __init__(self, model, view):
        TextField.__init__(self, model, view)
        self.view.searchChanged.connect(self.editingFinished)

