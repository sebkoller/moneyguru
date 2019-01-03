@SHEBANG@
# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import sys
import gc
import logging
import os.path as op

from PyQt5.QtCore import QFile, QTextStream
from PyQt5.QtGui import QIcon, QPixmap
from PyQt5.QtWidgets import QApplication

import core.trans
from core.args import get_parser
from qt.support.error_report_dialog import install_excepthook
from qt.util import setupQtLogging
import qt.mg_rc # noqa

def main():
    parser = get_parser()
    args = parser.parse_args()
    app = QApplication([])
    app.setWindowIcon(QIcon(QPixmap(":/logo_small")))
    app.setOrganizationName('Hardcoded Software')
    app.setApplicationName('moneyGuru')
    if args.debug:
        LOGGING_LEVEL = logging.DEBUG
    else:
        LOGGING_LEVEL = logging.WARNING
    setupQtLogging(level=LOGGING_LEVEL)
    logging.debug('started in debug mode')
    stylesheetFile = QFile(':/stylesheet_lnx')
    stylesheetFile.open(QFile.ReadOnly)
    textStream = QTextStream(stylesheetFile)
    style = textStream.readAll()
    stylesheetFile.close()
    app.setStyleSheet(style)
    locale_folder = op.join('@SHAREPATH@', 'locale')
    core.trans.install_gettext_trans(locale_folder)
    core.trans.install_qt_trans()
    # Many strings are translated at import time, so this is why we only import after the translator
    # has been installed
    from qt.app import MoneyGuru
    app.setApplicationVersion(MoneyGuru.VERSION)
    MoneyGuru.DOC_PATH = op.join('@DOCPATH@', 'index.html')
    mgapp = MoneyGuru(filepath=args.filepath)
    install_excepthook('https://github.com/hsoft/moneyguru/issues')
    exec_result = app.exec_()
    del mgapp
    # Since PyQt 4.7.2, I had crashes on exit, and from reading the mailing list, it seems to be
    # caused by some weird crap about C++ instance being deleted with python instance still living.
    # The worst part is that Phil seems to say this is expected behavior. So, whatever, this
    # gc.collect() below is required to avoid a crash.
    gc.collect()
    return exec_result

if __name__ == "__main__":
    sys.exit(main())
