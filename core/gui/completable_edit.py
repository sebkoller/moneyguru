# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.util import nonone, dedupe

from .base import DocumentGUIObject
from ..model.completion import CompletionList

class CompletableEdit(DocumentGUIObject):
    def __init__(self, mainwindow):
        super().__init__(mainwindow.document)
        self.mainwindow = mainwindow
        self._attrname = ''
        self._completions = None
        self._complete_completion = ''
        self.completion = ''
        self._text = ''
        # If doing completion for an entry table, set the account attribute
        self.account = None

    # --- Private
    def _revalidate(self):
        if self.mainwindow is None or not self.attrname:
            return
        doc = self.mainwindow.document
        attrname = self.attrname
        if attrname == 'description':
            self._candidates = doc.transactions.descriptions
        elif attrname == 'payee':
            self._candidates = doc.transactions.payees
        elif attrname in {'from', 'to', 'account', 'transfer'}:
            result = doc.transactions.account_names
            # `result` doesn't contain empty accounts' name, so we'll add them.
            result += [a.name for a in doc.accounts if not a.inactive]
            if attrname == 'transfer' and self.account is not None:
                result = [name for name in result if name != self.account.name]
            self._candidates = result
        self._candidates = dedupe([name for name in self._candidates if name.strip()])

    def _set_completion(self, completion):
        completion = nonone(completion, '')
        self._complete_completion = completion
        self.completion = completion[len(self._text):]
        if self.completion:
            self.view.refresh()

    # --- Override
    # We override view to allow it to be set multiple times because
    # CompletableEdit, as a special case, can have more than one view swapping
    # each other out
    @property
    def view(self):
        return self._view

    @view.setter
    def view(self, value):
        self._view = value

    # --- Public
    def commit(self):
        """Accepts current completion and updates the text with it.

        If the text is a substring of the completion, completion's case will prevail. If, however,
        the completion is the same length as the text, it means that the user completly types the
        string. In this case, we assume that the user wants his own case to prevail.
        """
        if len(self._text) < len(self._complete_completion):
            self._text = self._complete_completion
            self.completion = ''
            self.view.refresh()

    def down(self):
        if self._completions:
            self._set_completion(self._completions.prev())

    def up(self):
        if self._completions:
            self._set_completion(self._completions.next())

    def lookup(self):
        self.mainwindow.completion_lookup.show(self)

    def set_lookup_choice(self, text):
        self._text = text
        self.completion = ''
        self.view.refresh()

    # --- Properties
    @property
    def attrname(self):
        return self._attrname

    @attrname.setter
    def attrname(self, value):
        if self._attrname == value:
            return
        self._attrname = value
        self.invalidate()
        self._text = ''
        self._set_completion('')
        self._completions = None

    @property
    def candidates(self):
        self.revalidate()
        return self._candidates

    @property
    def text(self):
        return self._text

    @text.setter
    def text(self, value):
        self._text = value
        if self.candidates:
            self._completions = CompletionList(value, self._candidates)
            self._set_completion(self._completions.current())
        else:
            self._completions = None
