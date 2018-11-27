# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os.path as op

from PyQt5.QtCore import (
    pyqtSignal, QCoreApplication, QLocale, QUrl, QStandardPaths, QTimer,
    QObject)
from PyQt5.QtGui import QDesktopServices
from PyQt5.QtWidgets import QDialog, QApplication, QMessageBox


from core.app import Application as MoneyGuruModel

from .controller.document import Document
from .controller.main_window import MainWindow
from .controller.preferences_panel import PreferencesPanel
from .support.about_box import AboutBox
from .support.date_edit import DateEdit
from .preferences import Preferences
from .plat import HELP_PATH
from .util import getAppData

class MoneyGuru(QObject):
    VERSION = MoneyGuruModel.VERSION
    LOGO_NAME = 'logo'

    def __init__(self, filepath=None):
        QObject.__init__(self)
        QTimer.singleShot(0, self.__launchTimerTimedOut)
        self.prefs = Preferences()
        self.prefs.load()
        global APP_PREFS
        APP_PREFS = self.prefs
        locale = QLocale.system()
        dateFormat = self.prefs.dateFormat
        decimalSep = locale.decimalPoint()
        groupingSep = locale.groupSeparator()
        cachePath = QStandardPaths.standardLocations(QStandardPaths.CacheLocation)[0]
        appdata = getAppData()
        DateEdit.DATE_FORMAT = dateFormat
        self.model = MoneyGuruModel(
            view=self, date_format=dateFormat, decimal_sep=decimalSep,
            grouping_sep=groupingSep, cache_path=cachePath, appdata_path=appdata,
        )
        # on the Qt side, we're single document based, so it's one doc per app.
        self.doc = Document(app=self)
        self.doc.model.connect()
        self.mainWindow = MainWindow(doc=self.doc)
        self.preferencesPanel = PreferencesPanel(self.mainWindow, app=self)
        self.aboutBox = AboutBox(self.mainWindow, self)
        self.initialFilePath = None
        if filepath and op.exists(filepath):
            self.initialFilePath = filepath
        elif self.prefs.recentDocuments:
            self.initialFilePath = self.prefs.recentDocuments[0]

        self.finishedLaunching.connect(self.applicationFinishedLaunching)
        QCoreApplication.instance().aboutToQuit.connect(self.applicationWillTerminate)

    # --- Public
    def showAboutBox(self):
        self.aboutBox.show()

    def showHelp(self):
        help_path = op.abspath(op.join(HELP_PATH, 'index.html'))
        if op.exists(help_path):
            url = QUrl.fromLocalFile(help_path)
        else:
            url = QUrl("https://www.hardcoded.net/moneyguru/help/en")
        QDesktopServices.openUrl(url)

    def showPreferences(self):
        self.preferencesPanel.load()
        if self.preferencesPanel.exec_() == QDialog.Accepted:
            self.preferencesPanel.save()
            self.prefs.prefsChanged.emit()

    # --- Event Handling
    def applicationFinishedLaunching(self):
        self.prefs.restoreGeometry('mainWindowGeometry', self.mainWindow)
        self.prefs.restoreGeometry('importWindowGeometry', self.mainWindow.importWindow)
        self.mainWindow.show()
        if self.initialFilePath:
            self.doc.open(self.initialFilePath, initial=True)

    def applicationWillTerminate(self):
        self.doc.close()
        self.willSavePrefs.emit()
        self.prefs.saveGeometry('mainWindowGeometry', self.mainWindow)
        self.prefs.saveGeometry('importWindowGeometry', self.mainWindow.importWindow)
        self.prefs.save()
        self.model.shutdown()

    # --- Signals
    def __launchTimerTimedOut(self):
        self.finishedLaunching.emit()

    finishedLaunching = pyqtSignal()
    willSavePrefs = pyqtSignal()

    # --- model --> view
    def get_default(self, key):
        return self.prefs.get_value(key)

    def set_default(self, key, value):
        self.prefs.set_value(key, value)

    def show_message(self, msg):
        window = QApplication.activeWindow()
        QMessageBox.information(window, '', msg)

    def open_url(self, url):
        url = QUrl(url)
        QDesktopServices.openUrl(url)

    def reveal_path(self, path):
        url = QUrl.fromLocalFile(str(path))
        QDesktopServices.openUrl(url)

