# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from PyQt5.QtWidgets import QFormLayout, QComboBox, QSizePolicy

from core.trans import trget

from .base_view import BaseView
from .selectable_list import ComboboxModel

tr = trget('ui')

class DocPropsView(BaseView):
    def _setup(self):
        self._setupUi()
        self.currencyComboBox = ComboboxModel(model=self.model.currency_list, view=self.currencyComboBoxView)
        self.firstWeekdayComboBox = ComboboxModel(
            model=self.model.first_weekday_list,
            view=self.firstWeekdayComboBoxView
        )
        self.aheadMonthsComboBox = ComboboxModel(
            model=self.model.ahead_months_list,
            view=self.aheadMonthsComboBoxView
        )
        self.yearStartComboBox = ComboboxModel(
            model=self.model.year_start_month_list,
            view=self.yearStartComboBoxView
        )

    def _setupUi(self):
        self.mainLayout = QFormLayout(self)

        sizePolicy = QSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.currencyComboBoxView = QComboBox()
        self.currencyComboBoxView.setEditable(True)
        self.currencyComboBoxView.setInsertPolicy(QComboBox.NoInsert)
        self.currencyComboBoxView.setSizePolicy(sizePolicy)
        self.mainLayout.addRow(tr("Native Currency:"), self.currencyComboBoxView)

        self.firstWeekdayComboBoxView = QComboBox(self)
        self.firstWeekdayComboBoxView.setSizePolicy(sizePolicy)
        self.mainLayout.addRow(tr("First day of the week:"), self.firstWeekdayComboBoxView)

        self.aheadMonthsComboBoxView = QComboBox(self)
        self.aheadMonthsComboBoxView.setSizePolicy(sizePolicy)
        self.mainLayout.addRow(tr("Ahead months in Running Year:"), self.aheadMonthsComboBoxView)

        self.yearStartComboBoxView = QComboBox(self)
        self.yearStartComboBoxView.setSizePolicy(sizePolicy)
        self.mainLayout.addRow(tr("Year starts in:"), self.yearStartComboBoxView)

