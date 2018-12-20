# Copyright 2016 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.trans import trget
from .column import Column

from .table import GUITable, Row

trcol = trget('columns')

class PluginListTable(GUITable):
    SAVENAME = 'PluginListTable'
    COLUMNS = [
        Column('enabled', display=trcol("Enabled")),
        Column('name', display=trcol("Name")),
        Column('type', display=trcol("Type")),
        Column('author', display=trcol("Author")),
    ]

    # --- Override
    def _fill(self):
        for plugin in self.document.app.plugins:
            self.append(PluginListRow(self, plugin))


class PluginListRow(Row):
    def __init__(self, table, plugin):
        Row.__init__(self, table)
        self.document = table.document
        self.plugin = plugin
        self.load()

    # --- Public
    def load(self):
        self._enabled = self.document.app.is_plugin_enabled(self.plugin)
        self.name = self.plugin.NAME
        self.type = self.plugin.TYPE_NAME
        self.author = self.plugin.AUTHOR

    def save(self):
        pass # read-only

    # --- Properties
    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, value):
        self.document.app.set_plugin_enabled(self.plugin, value)
        self._enabled = self.document.app.is_plugin_enabled(self.plugin)


