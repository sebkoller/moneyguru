# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import csv

from ..model._ccore import amount_format
from ..model.date import format_date

# account_pairs: (account, entries)
def save(filename, account_pairs, daterange=None):
    fp = open(filename, 'wt', encoding='utf-8')
    writer = csv.writer(fp, delimiter=';', quotechar='"')
    HEADER = ['Account', 'Date', 'Description', 'Payee', 'Check #', 'Transfer', 'Amount', 'Currency']
    writer.writerow(HEADER)
    for account, entries in account_pairs:
        if daterange is not None:
            entries = [e for e in entries if e.date in daterange]
        for entry in entries:
            date_str = format_date(entry.date, 'dd/MM/yyyy')
            transfer = ', '.join(a.name for a in entry.transfer)
            amount = entry.amount
            if amount:
                amount_fmt = amount_format(amount, amount.currency_code)
                currency_code = amount.currency_code
            else:
                amount_fmt = '0.00'
                currency_code = ''
            row = [
                account.name, date_str, entry.description, entry.payee, entry.checkno, transfer,
                amount_fmt, currency_code
            ]
            writer.writerow(row)
    fp.close()

