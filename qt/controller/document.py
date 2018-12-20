# Created By: Virgil Dupras
# Created On: 2009-10-31
# Copyright 2015 Hardcoded Software (http://www.hardcoded.net)
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os.path as op
import tempfile

from PyQt5.QtCore import pyqtSignal, Qt, QObject, QFile
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QApplication

from core.trans import trget
from core.exception import FileFormatError
from core.document import Document as DocumentModel, ScheduleScope

from ..controller.schedule_scope_dialog import ScheduleScopeDialog

tr = trget('ui')

class Document(QObject):
    def __init__(self, app):
        QObject.__init__(self)
        self.app = app
        self.documentPath = None
        self.model = DocumentModel(app=app.model)
        self.model.view = self

    # --- Public
    def close(self):
        if self.documentPath:
            self.model.close()

    def confirmDestructiveAction(self):
        # Asks whether the user wants to continue before continuing with an action that will replace
        # the current document. Will save the document as needed. Returns True if the action can
        # continue.
        if not self.model.is_dirty():
            return True
        title = tr("Unsaved Document")
        msg = tr("Do you want to save your changes before continuing?")
        buttons = QMessageBox.Save | QMessageBox.Cancel | QMessageBox.Discard
        result = QMessageBox.question(self.app.mainWindow, title, msg, buttons)
        if result == QMessageBox.Save:
            self.save()
            if self.model.is_dirty(): # "save as" was cancelled
                return False
            else:
                return True
        elif result == QMessageBox.Cancel:
            return False
        elif result == QMessageBox.Discard:
            return True

    def new(self):
        if not self.confirmDestructiveAction():
            return
        self.close()
        self.documentPath = None
        self.model.clear()
        self.documentPathChanged.emit()

    def open(self, docpath, initial=False):
        # initial flag is true when open() is called at the document's initialization. When that's
        # the case, we need to create a new document when we fail opening this one.
        if not self.confirmDestructiveAction():
            return
        self.close()
        try:
            self.model.load_from_xml(docpath)
            self.documentPath = docpath
        except FileFormatError as e:
            QMessageBox.warning(self.app.mainWindow, tr("Cannot load file"), str(e))
            if initial:
                self.new()
        self.documentPathChanged.emit()
        self.documentOpened.emit(docpath)

    def openDocument(self):
        title = tr("Select a document to load")
        filters = tr("moneyGuru Documents (*.moneyguru)")
        docpath, filetype = QFileDialog.getOpenFileName(self.app.mainWindow, title, '', filters)
        if docpath:
            self.open(docpath)

    def openExampleDocument(self):
        if not self.confirmDestructiveAction():
            return
        self.close()
        dirpath = tempfile.mkdtemp()
        destpath = op.join(dirpath, 'example.moneyguru')
        QFile.copy(':/example.moneyguru', destpath)
        self.model.load_from_xml(destpath)
        self.model.adjust_example_file()
        self.documentPath = None # As if it was a new doc. Save As is required.
        self.documentPathChanged.emit()

    def save(self):
        if self.documentPath is not None:
            self.model.save_to_xml(self.documentPath)
        else:
            self.saveAs()

    def saveAs(self):
        title = tr("Save As")
        filters = tr("moneyGuru Documents (*.moneyguru)")
        docpath = QFileDialog.getSaveFileName(self.app.mainWindow, title, '', filters)[0]
        if docpath:
            if not docpath.endswith('.moneyguru'):
                docpath += '.moneyguru'
            self.model.save_to_xml(docpath)
            self.documentPath = docpath
            self.documentPathChanged.emit()
            self.documentSavedAs.emit(docpath)

    # model --> view
    def query_for_schedule_scope(self):
        if QApplication.keyboardModifiers() & Qt.ShiftModifier:
            return ScheduleScope.Global
        if not self.app.model.show_schedule_scope_dialog:
            return ScheduleScope.Local
        dialog = ScheduleScopeDialog(self.app.mainWindow)
        return dialog.queryForScope()

    # --- Signals
    documentOpened = pyqtSignal(str)
    documentSavedAs = pyqtSignal(str)
    documentPathChanged = pyqtSignal()
