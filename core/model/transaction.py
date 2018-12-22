# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ._ccore import Transaction as _Transaction

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

def splitted_splits(splits):
    """Returns `splits` separated in two groups ("froms" and "tos").

    "froms" are splits with a negative amount and "tos", the positive ones. Null splits are
    generally sent to the "froms" side, unless "tos" is empty.

    Returns ``(froms, tos)``.
    """
    null_amounts = [s for s in splits if s.amount == 0]
    froms = [s for s in splits if s.amount < 0]
    tos = [s for s in splits if s.amount > 0]
    if not tos and null_amounts:
        tos.append(null_amounts.pop())
    froms += null_amounts
    return froms, tos

def Transaction(date, description=None, payee=None, checkno=None, account=None, amount=None):
    return _Transaction(1, date, description, payee, checkno, account, amount)
