# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import re
import unicodedata

from ..const import AccountType

# The range of diacritics in Unicode
diacritics = re.compile('[\u0300-\u036f\u1dc0-\u1dff]')

def sort_string(s):
    """Returns a normalized version of 's' to be used for sorting.
    """
    return diacritics.sub('', unicodedata.normalize('NFD', str(s)).lower())

ACCOUNT_SORT_KEY = lambda a: (AccountType.InOrder.index(a.type), sort_string(a.name))
