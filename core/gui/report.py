# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import csv
from io import StringIO

from core.trans import tr

from ..model.sort import ACCOUNT_SORT_KEY
from ..util import extract
from .column import Columns
from .base import ViewChild
from . import tree

# used in both bsheet and istatement
def get_delta_perc(delta_amount, start_amount):
    if start_amount:
        return '%+1.1f%%' % (delta_amount / abs(start_amount) * 100)
    else:
        return '---'

def new_name(base_name, search_func):
    name = base_name
    index = 0
    while search_func(name) is not None:
        index += 1
        name = '%s %d' % (base_name, index)
    return name

class Report(ViewChild, tree.Tree):
    SAVENAME = ''
    COLUMNS = []

    def __init__(self, parent_view):
        ViewChild.__init__(self, parent_view)
        tree.Tree.__init__(self)
        self.columns = Columns(self, prefaccess=parent_view.document, savename=self.SAVENAME)
        self.edited = None
        self._expanded_paths = {(0, ), (1, )}

    # --- Override
    def restore_view(self):
        prefname = '{}.ExpandedPaths'.format(self.SAVENAME)
        expanded = self.document.get_default(prefname, list())
        if expanded:
            self._expanded_paths = {tuple(p) for p in expanded}
            self.view.refresh_expanded_paths()
        self.columns.restore_columns()

    # --- Virtual
    def _compute_account_node(self, node):
        pass

    def _make_node(self, name):
        node = Node(name)
        node.account_number = ''
        return node

    def _refresh(self):
        pass

    # --- Protected
    def _node_of_account(self, account):
        return self.find(lambda n: getattr(n, 'account', None) == account)

    def _prune_invalid_expanded_paths(self):
        newpaths = set()
        for path in self._expanded_paths:
            try:
                node = self.get_node(path)
                if node.is_group or node.is_type:
                    newpaths.add(path)
            except IndexError:
                pass
        self._expanded_paths = newpaths

    def _select_first(self):
        for type_node in self:
            if len(type_node) > 2: # total + blank
                self.selected = type_node[0]
                break

    def _update_selection(self):
        if not (isinstance(self.selected, Node) and self.selected.is_account):
            self._select_first()

    # --- Public
    def add_account(self):
        self.view.stop_editing()
        self.stop_editing()
        node = self.selected
        if isinstance(node, Node) and node.is_group:
            account_type = node.parent.type
            account_group = node.name
        elif isinstance(node, Node) and node.is_account:
            account_type = node.account.type
            account_group = node.account.groupname
        else:
            # there are only 2 types per report
            path = self.selected_path
            account_type = self[1].type if path and path[0] == 1 else self[0].type
            account_group = None
        if account_group:
            self.parent_view.expand_group(account_group, account_type)
        account = self.document.new_account(account_type, account_group)
        self.mainwindow.revalidate()
        self.selected = self._node_of_account(account)
        self.view.update_selection()
        self.view.start_editing()

    def add_account_group(self):
        self.view.stop_editing()
        self.stop_editing()
        node = self.selected
        while node is not None and not node.is_type:
            node = node.parent
        if node is None:
            node = self[0]

        def findname(name):
            return node.find(lambda n: n.is_group and n.name.lower() == name.lower())

        name = new_name(tr("New group"), findname)
        self.document.newgroups.add((name, node.type))
        self.document.touch()
        self.mainwindow.revalidate()
        self.selected = self.find(
            lambda n: n.name == name and n.is_group and n.parent.type == node.type)
        self.view.update_selection()
        self.view.start_editing()

    def can_delete(self):
        node = self.selected
        return isinstance(node, Node) and (node.is_account or node.is_group)

    def can_move(self, source_paths, dest_path):
        """Returns whether it's possible to move the nodes at 'source_paths' under the node at
        'dest_path'.
        """
        if not dest_path:  # Don't move under the root
            return False
        dest_node = self.get_node(dest_path)
        if not (dest_node.is_group or dest_node.is_type):
            # Move only under a group node or a type node
            return False
        for source_path in source_paths:
            source_node = self.get_node(source_path)
            if not source_node.is_account:
                return False
            if source_node.parent is dest_node:  # Don't move under the same node
                return False
        return True

    def cancel_edits(self):
        # The behavior for calling view.stop_editing() in Report is a bit
        # different than with tables: we *always* call it instead of calling it
        # only when something is edited. I'm not sure why. Comments in tests
        # talk about causing crashes. TODO: investigate and clarify comment.
        self.view.stop_editing()
        node = self.edited
        if node is None:
            return
        assert node.is_account or node.is_group
        node.name = node.account.name if node.is_account else node.oldname
        self.edited = None

    def collapse_node(self, node):
        self._expanded_paths.discard(tuple(node.path))
        if node.is_group:
            self.parent_view.collapse_group(node.name, node.parent.type)

    def delete(self):
        if not self.can_delete():
            return
        self.view.stop_editing()
        selected_nodes = self.selected_nodes
        gnodes = [n for n in selected_nodes if n.is_group]
        for node in gnodes:
            accounts = self.document.accounts.filter(
                groupname=node.name, type=node.parent.type)
            if accounts:
                self.document.change_accounts(accounts, groupname=None)
            self.document.newgroups.discard((node.name, node.parent.type))
            self.document.touch()
        anodes = [n for n in selected_nodes if n.is_account]
        if anodes:
            accounts = [n.account for n in anodes]
            if any(self.document.accounts.entries_for_account(a) for a in accounts):
                panel = self.parent_view.get_account_reassign_panel()
                panel.load(accounts)
            else:
                self.document.delete_accounts(accounts)
        self.mainwindow.revalidate()

    def expand_node(self, node):
        self._expanded_paths.add(tuple(node.path))
        if node.is_group:
            self.parent_view.expand_group(node.name, node.parent.type)

    def make_account_node(self, account):
        node = self._make_node(account.name)
        node.account = account
        node.is_account = True
        node.account_number = account.account_number
        node.is_excluded = account in self.document.excluded_accounts
        if not node.is_excluded:
            self._compute_account_node(node)
        return node

    def make_blank_node(self):
        node = self._make_node(None)
        node.is_blank = True
        return node

    def make_group_node(self, groupname, grouptype):
        node = self._make_node(groupname)
        node.is_group = True
        node.oldname = groupname # in case we rename
        accounts = self.document.accounts.filter(
            groupname=groupname, type=grouptype)
        for account in sorted(accounts, key=ACCOUNT_SORT_KEY):
            node.append(self.make_account_node(account))
        node.is_excluded = bool(accounts) and set(accounts) <= self.document.excluded_accounts # all accounts excluded
        if not node.is_excluded:
            node.append(self.make_total_node(node, tr('Total ') + groupname))
        node.append(self.make_blank_node())
        return node

    def make_total_node(self, name):
        node = self._make_node(name)
        node.is_total = True
        return node

    def make_type_node(self, name, type):
        node = self._make_node(name)
        node.type = type
        node.is_type = True
        accounts = self.document.accounts.filter(type=type)
        grouped, ungrouped = extract(lambda a: bool(a.groupname), accounts)
        groupnames = {a.groupname for a in grouped}
        groupnames |= {n for n, t in self.document.newgroups if t == type}
        for groupname in sorted(groupnames):
            node.append(self.make_group_node(groupname, type))
        for account in sorted(ungrouped, key=ACCOUNT_SORT_KEY):
            node.append(self.make_account_node(account))
        accounts = self.document.accounts.filter(type=type)
        node.is_excluded = bool(accounts) and set(accounts) <= self.document.excluded_accounts # all accounts excluded
        if not node.is_excluded:
            node.append(self.make_total_node(node, tr('TOTAL ') + name))
        node.append(self.make_blank_node())
        return node

    def move(self, source_paths, dest_path):
        """Moves the nodes at 'source_paths' under the node at 'dest_path'."""
        assert self.can_move(source_paths, dest_path)
        accounts = [self.get_node(p).account for p in source_paths]
        dest_node = self.get_node(dest_path)
        if dest_node.is_type:
            self.document.change_accounts(
                accounts, groupname=None, type=dest_node.type)
        elif dest_node.is_group:
            self.document.change_accounts(
                accounts, groupname=dest_node.name, type=dest_node.parent.type)
        self.mainwindow.revalidate()

    def refresh(self, refresh_view=True):
        selected_accounts = self.selected_accounts
        selected_paths = self.selected_paths
        self._refresh()
        selected_nodes = []
        for account in selected_accounts:
            node_of_account = self._node_of_account(account)
            if node_of_account is not None:
                selected_nodes.append(node_of_account)
        if selected_nodes:
            self.selected_nodes = selected_nodes
        elif len(selected_paths) == 1 and len(selected_paths[0]) > 1:
            # If our selected path is not an account or group (because of a
            # deletion, most probably), try to select the node preceding it so
            # that our selection stays in the realm of accounts/groups.
            selected_path = selected_paths[0]
            try:
                next_node = self.get_node(selected_path)
            except IndexError:
                self._select_first()
            else:
                if not (next_node.is_account or next_node.is_group):
                    selected_path[-1] -= 1
                    if selected_path[-1] < 0:
                        selected_path = selected_path[:-1]
                self.selected_path = selected_path
        elif selected_paths:
            self.selected_paths = selected_paths
        else:
            self._select_first()
        self._prune_invalid_expanded_paths()
        if refresh_view:
            self.view.refresh()

    def save_edits(self):
        node = self.edited
        if node is None:
            return
        self.edited = None
        assert node.is_account or node.is_group
        if node.is_account:
            success = self.document.change_accounts([node.account], name=node.name)
        else:
            other = node.parent.find(
                lambda n: n.is_group and n.name.lower() == node.name.lower())
            success = other is None or other is node
            if success:
                accounts = self.document.accounts.filter(
                    groupname=node.oldname, type=node.parent.type)
                if accounts:
                    self.document.change_accounts(accounts, groupname=node.name)
                else:
                    self.document.touch()
                self.document.newgroups.discard((node.oldname, node.parent.type))
                self.document.newgroups.add((node.name, node.parent.type))
        self.mainwindow.revalidate()
        if not success:
            msg = tr("The account '{0}' already exists.").format(node.name)
            # we use _name because we don't want to change self.edited
            node._name = node.account.name if node.is_account else node.oldname
            self.mainwindow.show_message(msg)

    def save_preferences(self):
        # Save node expansion state
        prefname = '{}.ExpandedPaths'.format(self.SAVENAME)
        self.document.set_default(prefname, self.expanded_paths)
        self.columns.save_columns()

    def selection_as_csv(self):
        csvrows = []
        columns = (self.columns.coldata[colname] for colname in self.columns.colnames)
        columns = [col for col in columns if col.visible]
        for node in self.selected_nodes:
            csvrow = []
            for col in columns:
                try:
                    csvrow.append(getattr(node, col.name))
                except AttributeError:
                    pass
            csvrows.append(csvrow)
        fp = StringIO()
        csv.writer(fp, delimiter='\t', quotechar='"').writerows(csvrows)
        fp.seek(0)
        return fp.read()

    def show_selected_account(self):
        self.mainwindow.open_account(self.selected_account)

    def show_account(self, path):
        node = self.get_node(path)
        self.mainwindow.open_account(node.account)

    def stop_editing(self):
        self.view.stop_editing()
        if self.edited is not None:
            self.save_edits()

    def toggle_excluded(self):
        nodes = self.selected_nodes
        affected_accounts = set()
        for node in nodes:
            if node.is_type:
                affected_accounts |= set(self.document.accounts.filter(type=node.type))
            elif node.is_group:
                accounts = self.document.accounts.filter(
                    groupname=node.name, type=node.parent.type)
                affected_accounts |= set(accounts)
            elif node.is_account:
                affected_accounts.add(node.account)
        if affected_accounts:
            self.parent_view.toggle_accounts_exclusion(affected_accounts)

    # --- Properties
    @property
    def can_show_selected_account(self):
        return self.selected_account is not None

    @property
    def expanded_paths(self):
        paths = list(self._expanded_paths)
        # We want the paths in orthe of length so that the paths are correctly expanded in the gui.
        paths.sort(key=lambda p: (len(p), ) + p)
        return paths

    selected = tree.Tree.selected_node

    @property
    def selected_account(self):
        accounts = self.selected_accounts
        if accounts:
            return accounts[0]
        else:
            return None

    @property
    def selected_accounts(self):
        nodes = self.selected_nodes
        return [node.account for node in nodes if node.is_account]


class Node(tree.Node):
    def __init__(self, name):
        tree.Node.__init__(self, name)
        self.is_account = False
        self.is_blank = False
        self.is_group = False
        self.is_total = False
        self.is_type = False
        self.is_excluded = False

    @property
    def is_expanded(self):
        return tuple(self.path) in self.root._expanded_paths

    @property
    def is_subtotal(self):
        if not (self.is_account or self.is_group):
            return False
        if len(self) and self.is_expanded: # an expanded group can't be considered a subtotal
            return False
        parent = self.parent
        if parent is None:
            return False
        index = parent.index(self)
        try:
            next_node = parent[index+1]
            return next_node.is_total
        except IndexError:
            return False

    @property
    def can_edit_name(self):
        return self.is_account or self.is_group

    @tree.Node.name.setter
    def name(self, value):
        root = self.root
        assert root.edited is None or root.edited is self
        if not value:
            return
        self._name = value
        root.edited = self

