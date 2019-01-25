# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

from ..const import AccountType
from ..model.date import format_date

# account_pairs: (account, entries)
def save(filename, account_pairs, daterange=None):
    def format_amount_for_qif(amount):
        return '%1.2f' % float(amount) if amount else '0.00'

    account_pairs = [(a, e) for a, e in account_pairs if a.is_balance_sheet_account()]
    lines = []
    for account, entries in account_pairs:
        qif_account_type = 'Oth L' if account.type == AccountType.Liability else 'Bank'
        lines.append('!Account')
        lines.append('N%s' % account.name)
        balance = entries.balance(None, account.currency)
        lines.append('B%s' % format_amount_for_qif(balance))
        lines.append('T%s' % qif_account_type)
        lines.append('^')
        lines.append('!Type:%s' % qif_account_type)
        if daterange is not None:
            entries = [e for e in entries if e.date in daterange]
        for entry in entries:
            lines.append('D%s' % format_date(entry.date, 'MM/dd/yyyy'))
            lines.append('T%s' % format_amount_for_qif(entry.amount))
            if entry.description:
                lines.append('M%s' % entry.description)
            if entry.payee:
                lines.append('P%s' % entry.payee)
            if entry.checkno:
                lines.append('N%s' % entry.checkno)
            if len(entry.splits) > 1 or any(s.memo for s in entry.transaction.splits):
                for split in entry.splits:
                    if split.account is not None:
                        lines.append('S%s' % split.account.name)
                    if split.memo:
                        lines.append('E%s' % split.memo)
                    if split.reconciled:
                        lines.append('CR')
                    lines.append('$%s' % format_amount_for_qif(-split.amount))
            else:
                if entry.transfer:
                    lines.append('L%s' % entry.transfer[0].name)
                if entry.reconciled:
                    lines.append('CR')
            lines.append('^')
    fd = open(filename, 'wt', encoding='utf-8')
    fd.write('\n'.join(lines))
    fd.close()
