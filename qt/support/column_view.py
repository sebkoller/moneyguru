# Copyright 2014 Nelson Brown
# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from collections import namedtuple

from PyQt5.QtCore import QRectF, QSize, Qt
from PyQt5.QtGui import QTextOption, QPalette
from PyQt5.QtWidgets import QStyleOptionViewItem, QStyle

import re
import logging

from hscommon.util import nonone

CURR_VALUE_RE = re.compile(r"([^\d]{3} )?(.*)")

# Simple named tuple to separate the currency from the value
DisplayAmount = namedtuple('DisplayAmount', 'currency value')

class AmountPainter:

    def __init__(self, attr_name, model):
        self._attr_name = attr_name
        self._model = model

    # private functions
    def _getDataFromIndex(self, index):
        """Retrieves model amount data and converts it to a DisplayAmount.


        Retrieves the amount string from the model based on the column name.
        Uses a regular expression to parse this string, converting it into
        a DisplayAmount to be returned.

        Args:
            index - QModelIndex in the model

        Returns:
            None if the data is not in the model or the regular expression
            failed to parse the data.

            A DisplayAmount with currency and value information used to
            perform amount painting. For example:

            "MXN 432 321,01" -> DisplayAmount("MXN", "432 321,01")
        """
        if not index.isValid():
            return None
        column = self._model.columns.column_by_index(index.column())
        if column.name != self._attr_name:
            return None
        amount = getattr(self._model[index.row()], column.name)

        amount = CURR_VALUE_RE.match(amount)

        if amount is None:
            logging.warning("Amount for column %s index row %s "
                            "with amount '%s' did not match regular "
                            "expression for amount painting.",
                            column.name, index.row(), amount)
            return None

        amount = amount.groups()

        return DisplayAmount(nonone(amount[0], "").strip(), amount[1])

    def _getAmountTextWidths(self, amount, option):
        """Converts DisplayAmount into a tuple of currency and value widths.

        Uses the option parameter to calculate the font width of the currency
        and value strings stored in the DisplayAmount amount parameter.  Returns
        these widths in a tuple, respectively.  Returns a value for the currency
        width as the width of the string 'XXX' used for alignment purposes in the
        paint method.

        Args:
            amount - DisplayAmount containing currency and value strings
            option - QStyleOptionViewItem normally as passed to a paint event

        Returns:
            A tuple of the currency and value widths in the amount.
        """
        do_paint_currency = amount.currency != ""
        # Use the currently formatted string just remove the currency information
        # for separate painting.
        if do_paint_currency:
            cur_width = option.fontMetrics.width(amount.currency)
        else:
            if self._model.all_amounts_are_native:
                cur_width = 0
            else:
                cur_width = option.fontMetrics.width("XXX")
        val_width = option.fontMetrics.width(amount.value)

        # It seems that it some cases, our width is too tight. After a Qt
        # update, amounts started to not draw entirely in some rare cases.
        # Rounding problems? maybe. Adding 1 fixes the problem. See #501
        return cur_width + 1, val_width + 1

    def sizeHint(self, option, index):
        """sizeHint returns a QSize of the required size to draw the amount.

        Returns the size to draw the currency, value, and some spacing in between.

        Args:
            option - QStyleOptionViewItem normally as passed to a paint event
            index - QModelIndex in the model

        Returns:
            QSize of the required size to draw the amount
        """
        amount = self._getDataFromIndex(index)
        if amount is None:
            return None
        option = QStyleOptionViewItem(option)
        cur_width, val_width = self._getAmountTextWidths(amount, option)
        # Add some extra spacing in between (15) and padding on sides (5,5)
        return QSize(5+cur_width+15+val_width+5, option.fontMetrics.height())

    def paint(self, painter, option, index):
        """Paints the amount within the bounding box provided in the option parameter.

        Draws the currency left aligned and the value of the model amount right aligned.
        Some spacing between with left and right padding is also utilized.

        Args:
            painter - QPainter
            option - QStyleOptionViewItem
            index - QModelIndex in the model
        """
        column_data = self._getDataFromIndex(index)
        if column_data is None:
            return
        option = QStyleOptionViewItem(option)
        painter.setFont(option.font)
        cur_width, val_width = self._getAmountTextWidths(column_data, option)
        font_height = option.fontMetrics.height()
        do_paint_currency = cur_width > 0
        is_selected = bool(option.state & QStyle.State_Selected)
        is_active = bool(option.state & QStyle.State_Active)
        palette_active = QPalette.Active if is_active else QPalette.Inactive
        palette_text = QPalette.HighlightedText if is_selected else QPalette.Text
        pen_color = option.palette.color(palette_active, palette_text)
        painter.setPen(pen_color)

        if do_paint_currency:
            painter.drawText(QRectF(4+option.rect.left(),
                                    option.rect.top(),
                                    cur_width,
                                    font_height),
                             column_data.currency,
                             QTextOption(Qt.AlignVCenter))
        painter.drawText(QRectF(option.rect.right() - val_width - 5,
                                option.rect.top(),
                                val_width,
                                font_height),
                         column_data.value,
                         QTextOption(Qt.AlignVCenter))
