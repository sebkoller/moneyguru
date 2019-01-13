# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ._ccore import TransactionList as TransactionListBase

class TransactionList(TransactionListBase):
    """Manages the :class:`.Transaction` instances of a document.

    This class is mostly about managing transactions sorting order, moving them around and keeping
    a cache of values to use for completion. There's only one of those in a document, in
    :attr:`.Document.transactions`.
    """
    # --- Public
    def reassign_account(self, account, reassign_to=None):
        """Calls :meth:`.Transaction.reassign_account` on all transactions.

        If, after such an operation, a transaction ends up referencing no account at all, it is
        removed.
        """
        for transaction in list(self):
            transaction.reassign_account(account, reassign_to)
            if not transaction.affected_accounts():
                self.remove(transaction)
        self.clear_cache()

    def move_before(self, from_transaction, to_transaction):
        """Moves ``from_transaction`` just before ``to_transaction``.

        If ``to_transaction`` is ``None``, ``from_transaction`` is moved to the end of the
        list. You must :ref:`recook <cooking>` after having done a move (or a bunch of moves)
        """
        if from_transaction not in self:
            return
        if to_transaction is not None and to_transaction.date != from_transaction.date:
            to_transaction = None
        transactions = self.transactions_at_date(from_transaction.date)
        transactions.remove(from_transaction)
        if not transactions:
            return
        if to_transaction is None:
            target_position = max(t.position for t in transactions) + 1
        else:
            target_position = to_transaction.position
        from_transaction.position = target_position
        for transaction in transactions:
            if transaction.position >= target_position:
                transaction.position += 1

    def move_last(self, transaction):
        """Equivalent to :meth:`move_before` with ``to_transaction`` to ``None``."""
        self.move_before(transaction, None)
