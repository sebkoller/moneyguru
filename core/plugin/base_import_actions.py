# Copyright 2016 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import tr

from core.plugin import ImportActionPlugin

class BaseSwapFields(ImportActionPlugin):
    AUTHOR = "Nelson Brown"
    ENABLED_BY_DEFAULT = True

    def __init__(self):
        ImportActionPlugin.__init__(self)

    def _switch_function(self, transaction):
        pass

    def perform_action(self, import_document, transactions, panes, selected_rows=None):
        for txn in transactions:
            new = txn.replicate()
            self._switch_function(new)
            import_document.change_transaction(txn, new)


DAY = 'day'
MONTH = 'month'
YEAR = 'year'

def last_two_digits(year):
    return year - ((year // 100) * 100)

def swapped_date(date, first, second):
    attrs = {DAY: date.day, MONTH: date.month, YEAR: last_two_digits(date.year)}
    newattrs = {first: attrs[second], second: attrs[first]}
    if YEAR in newattrs:
        newattrs[YEAR] += 2000
    return date.replace(**newattrs)


def swap_format_elements(format, first, second):
    # format is a DateFormat
    swapped = format.copy()
    elems = swapped.elements
    TYPE2CHAR = {DAY: 'd', MONTH: 'M', YEAR: 'y'}
    first_char = TYPE2CHAR[first]
    second_char = TYPE2CHAR[second]
    first_index = [i for i, x in enumerate(elems) if x.startswith(first_char)][0]
    second_index = [i for i, x in enumerate(elems) if x.startswith(second_char)][0]
    elems[first_index], elems[second_index] = elems[second_index], elems[first_index]
    return swapped


class BaseSwapDateFields(BaseSwapFields):

    def __init__(self):
        BaseSwapFields.__init__(self)
        self._first_field = None
        self._second_field = None

    def _switch_function(self, transaction):
        transaction.date = swapped_date(transaction.date, self._first_field, self._second_field)

    def on_selected_pane_changed(self, selected_pane):
        self._change_name(selected_pane.parsing_date_format)

    def _change_name(self, parsing_date_format):
        basefmt = parsing_date_format
        swapped = swap_format_elements(basefmt, self._first_field, self._second_field)
        self.ACTION_NAME = "{} --> {}".format(basefmt.iso_format, swapped.iso_format)
        self.notify(self.action_name_changed)

    def can_perform_action(self, import_document, transactions, panes, selected_rows=None):
        try:
            for txn in transactions:
                swapped_date(txn.date, self._first_field, self._second_field)
            return True
        except ValueError:
            return False

    def perform_action(self, import_document, transactions, panes, selected_rows=None):
        BaseSwapFields.perform_action(self, import_document, transactions, panes, selected_rows=None)
        # Now, lets' change the date format on these panes
        for pane in panes:
            basefmt = pane.parsing_date_format
            swapped = swap_format_elements(basefmt, self._first_field, self._second_field)
            pane.parsing_date_format = swapped

        self._change_name(panes[0].parsing_date_format)


class SwapDayMonth(BaseSwapDateFields):

    NAME = "Swap Day and Month Import Action"
    ACTION_NAME = "<placeholder> Day <--> Month"
    PRIORITY = 1

    def __init__(self):
        BaseSwapDateFields.__init__(self)
        self._first_field = DAY
        self._second_field = MONTH


class SwapMonthYear(BaseSwapDateFields):

    NAME = "Swap Month and Year Import Action"
    ACTION_NAME = "<placeholder> Month <--> Year"
    PRIORITY = 2

    def __init__(self):
        BaseSwapDateFields.__init__(self)
        self._first_field = MONTH
        self._second_field = YEAR


class SwapDayYear(BaseSwapDateFields):

    NAME = "Swap Day and Year Import Action"
    ACTION_NAME = "<placeholder> Day <--> Year"
    PRIORITY = 3

    def __init__(self):
        BaseSwapDateFields.__init__(self)
        self._first_field = DAY
        self._second_field = YEAR


class SwapDescriptionPayeeAction(BaseSwapFields):

    NAME = "Swap Description Payee Import Action"
    ACTION_NAME = tr("Description <--> Payee")
    PRIORITY = 4

    def _switch_function(self, txn):
        txn.description, txn.payee = txn.payee, txn.description


class InvertAmountsPlugin(ImportActionPlugin):

    NAME = "Invert Amounts Import Action"
    AUTHOR = "Nelson Brown"
    ACTION_NAME = tr("Invert Amount")
    PRIORITY = 5
    ENABLED_BY_DEFAULT = True

    def perform_action(self, import_document, transactions, panes, selected_rows=None):
        for transaction in transactions:
            new = transaction.replicate()
            for split in new.splits:
                split.amount = -split.amount
            import_document.change_transaction(transaction, new)

