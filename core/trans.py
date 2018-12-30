# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# Doing i18n with GNU gettext for the core text gets complicated, so what I do is that I make the
# GUI layer responsible for supplying a tr() function.

import gettext

_trfunc = None
_trget = None

def tr(s, context=None):
    if _trfunc is None:
        return s
    else:
        if context:
            return _trfunc(s, context)
        else:
            return _trfunc(s)

def trget(domain):
    # Returns a tr() function for the specified domain.
    if _trget is None:
        return lambda s: tr(s, domain)
    else:
        return _trget(domain)

def set_tr(new_tr, new_trget=None):
    global _trfunc, _trget
    _trfunc = new_tr
    if new_trget is not None:
        _trget = new_trget

def install_gettext_trans(base_folder):

    def gettext_trget(domain):
        try:
            return gettext.translation(domain, localedir=base_folder).gettext
        except IOError:
            return lambda s: s

    default_gettext = gettext_trget('core')

    def gettext_tr(s, context=None):
        if not context:
            return default_gettext(s)
        else:
            trfunc = gettext_trget(context)
            return trfunc(s)

    set_tr(gettext_tr, gettext_trget)

def install_qt_trans():
    # So, we install the gettext locale, great, but we also should try to install qt_*.qm if
    # available so that strings that are inside Qt itself over which I have no control are in the
    # right language.
    from PyQt5.QtCore import QCoreApplication, QTranslator, QLocale, QLibraryInfo
    lang = str(QLocale.system().name())[:2]
    qmname = 'qt_%s' % lang
    qtr = QTranslator(QCoreApplication.instance())
    qtr.load(qmname, QLibraryInfo.location(QLibraryInfo.TranslationsPath))
    QCoreApplication.installTranslator(qtr)
