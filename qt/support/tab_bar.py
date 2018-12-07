# Copyright 2018 Virgil Dupras

# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

# Inspired from https://stackoverflow.com/a/20098415

from PyQt5.QtCore import pyqtSignal, QSize
from PyQt5.QtWidgets import QTabBar, QPushButton

class TabBarPlus(QTabBar):
    plusClicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.plusButton = QPushButton("+")
        self.plusButton.setParent(self)
        self.plusButton.clicked.connect(self.plusClicked.emit)
        self.movePlusButton()

    def sizeHint(self):
        sizeHint = super().sizeHint()
        width = sizeHint.width()
        height = sizeHint.height()
        return QSize(width+25, height)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.movePlusButton()

    def tabLayoutChange(self):
        super().tabLayoutChange()
        self.movePlusButton()

    def movePlusButton(self):
        MARGIN = 4
        tabsize = sum(self.tabRect(i).width() for i in range(self.count()))
        size = self.height() - MARGIN * 2
        if tabsize + MARGIN + size > self.width():
            # Too many tabs. Let's just hide our plus button.
            self.plusButton.setVisible(False)
        else:
            self.plusButton.move(tabsize + MARGIN, MARGIN)
            self.plusButton.resize(size, size)
            self.plusButton.setVisible(True)

