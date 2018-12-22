# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from core.util import allsame, first

from .amount import convert_amount, of_currency
from ._ccore import Split, Transaction as TransactionBase

def txn_matches(txn, query):
    """Return whether ``txn`` is matching ``query``.

    ``query`` is a ``dict`` of all criteria to look for (example: ``{'payee': 'Barber shop'}``.
    List of possible dict keys:

    * description
    * payee
    * checkno
    * memo
    * amount
    * account
    * group

    All of these queries are string-based, except ``amount``, which requires an
    :class:`.Amount`.

    Returns true if any criteria matches, false otherwise.
    """
    query_description = query.get('description')
    if query_description is not None:
        if query_description in txn.description.lower():
            return True
    query_payee = query.get('payee')
    if query_payee is not None:
        if query_payee in txn.payee.lower():
            return True
    query_checkno = query.get('checkno')
    if query_checkno is not None:
        if query_checkno == txn.checkno.lower():
            return True
    query_memo = query.get('memo')
    if query_memo is not None:
        for split in txn.splits:
            if query_memo in split.memo.lower():
                return True
    query_amount = query.get('amount')
    if query_amount is not None:
        query_value = float(query_amount) if query_amount else 0
        for split in txn.splits:
            split_value = float(split.amount) if split.amount else 0
            if query_value == abs(split_value):
                return True
    query_account = query.get('account')
    if query_account is not None:
        for split in txn.splits:
            if split.account and split.account.name.lower() in query_account:
                return True
    query_group = query.get('group')
    if query_group is not None:
        for split in txn.splits:
            if split.account and split.account.groupname and \
                    split.account.groupname.lower() in query_group:
                return True
    return False

class Transaction(TransactionBase):
    """A movement of money between two or more accounts at a specific date.

    Money movements that a transaction implies are listed in :attr:`splits`. The splits of a
    transaction *always balance*, which means that the sum of amounts in its splits is always zero.

    Whenever a potentially unbalancing operation is made on the splits, call :meth:`balance` to
    balance the transaction out.

    Initialization arguments are mostly just directly assigned to their relevant attributes in the
    transaction, except for ``account`` and ``amount`` (there is no such attributes). If specified,
    we initialize what would otherwise be an empty split list with two splits: One adding ``amount``
    to ``account``, and the other adding ``-amount`` to ``None`` (an unassigned split).
    """

    TYPE = 1 # Used in CCore

    def __init__(self, date, description=None, payee=None, checkno=None, account=None, amount=None):
        TransactionBase.__init__(
            self, self.TYPE, date, description, payee, checkno, account, amount)

    def mct_balance(self, new_split_currency):
        """Balances a :ref:`multi-currency transaction <multi-currency-txn>` using exchange rates.

        *This balancing doesn't occur automatically, it is a user-initiated action.*

        Sums up the value of all splits in ``new_split_currency``, using exchange rates for
        :attr:`date`. If not zero, create a new unassigned split with the opposite of that amount.

        Of course, we need to have called :meth:`balance` before we can call this.

        :param new_split_currency: :class:`.Currency`
        """
        converted_amounts = (convert_amount(split.amount, new_split_currency, self.date) for split in self.splits)
        converted_total = sum(converted_amounts)
        if converted_total != 0:
            target = first(s for s in self.splits if (s.account is None) and of_currency(s.amount, new_split_currency))
            if target is not None:
                target.amount -= converted_total
            else:
                self.add_split(Split(None, -converted_total))

    def reassign_account(self, account, reassign_to=None):
        """Reassign all splits from ``account`` to ``reassign_to``.

        All :attr:`splits` belonging to ``account`` will be changed to ``reassign_to``.

        :param account: :class:`.Account`
        :param reassign_to: :class:`.Account`
        """
        for split in self.splits:
            if split.account == account:
                split.reconciliation_date = None
                split.account = reassign_to

    def replicate(self):
        res = Transaction(self.date)
        res.copy_from(self)
        return res

    def splitted_splits(self):
        """Returns :attr:`splits` separated in two groups ("froms" and "tos").

        "froms" are splits with a negative amount and "tos", the positive ones. Null splits are
        generally sent to the "froms" side, unless "tos" is empty.

        Returns ``(froms, tos)``.
        """
        splits = self.splits
        null_amounts = [s for s in splits if s.amount == 0]
        froms = [s for s in splits if s.amount < 0]
        tos = [s for s in splits if s.amount > 0]
        if not tos and null_amounts:
            tos.append(null_amounts.pop())
        froms += null_amounts
        return froms, tos

    # --- Properties
    @property
    def amount(self):
        """*get/set*. :class:`.Amount`. Total amount of the transaction.

        In short, the sum of all positive :attr:`splits`.

        Can only be set if :attr:`can_set_amount` is true, that is, if we have less than two splits.
        When set, we'll set :attr:`splits` in order to create a two-way transaction of that amount,
        preserving from and to accounts if needed.
        """
        if self.is_mct:
            # We need an approximation for the amount value. What we do is we take the currency of the
            # first split and use it as a base currency. Then, we sum up all amounts, convert them, and
            # divide the sum by 2.
            splits_with_amount = [s for s in self.splits if s.amount != 0]
            currency = splits_with_amount[0].amount.currency_code
            convert = lambda a: convert_amount(abs(a), currency, self.date)
            amount_sum = sum(convert(s.amount) for s in splits_with_amount)
            return amount_sum * 0.5
        else:
            return sum(s.debit for s in self.splits)

    @property
    def can_set_amount(self):
        """*readonly*. ``bool``. Whether we can set :attr:`amount`.

        True is we have two or less splits of the same currency.
        """
        return (len(self.splits) <= 2) and (not self.is_mct)

    @property
    def has_unassigned_split(self):
        """*readonly*. ``bool``. Whether any of our splits is unassigned (None)."""
        return any(s.account is None for s in self.splits)

    @property
    def is_mct(self):
        """*readonly*. ``bool``. Whether our splits contain more than one currency."""
        splits_with_amount = (s for s in self.splits if s.amount != 0)
        try:
            return not allsame(s.amount.currency_code for s in splits_with_amount)
        except ValueError: # no split with amount
            return False

    @property
    def is_null(self):
        """*readonly*. ``bool``. Whether our splits all have null amounts."""
        return all(not s.amount for s in self.splits)
