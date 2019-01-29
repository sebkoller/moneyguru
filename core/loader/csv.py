# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import csv
import logging

from core.util import stripfalse
from core.trans import tr

from ..const import AccountType
from ..exception import FileFormatError, FileLoadError
from . import base

class CsvField:
    Date = 'date'
    Description = 'description'
    Payee = 'payee'
    Checkno = 'checkno'
    Transfer = 'transfer'
    Amount = 'amount'
    Increase = 'increase'
    Decrease = 'decrease'
    Currency = 'currency'
    Reference = 'reference'

MERGABLE_FIELDS = {CsvField.Description, CsvField.Payee}

class Loader(base.Loader):
    FILE_OPEN_MODE = 'rb'

    def __init__(self, default_currency, default_date_format=None):
        base.Loader.__init__(self, default_currency, default_date_format)
        self.columns = []
        self.lines = []
        self.dialect = None # last used dialect
        self.readcontent = b''

    # --- Private
    @staticmethod
    def _merge_columns(columns, lines):
        # For any columns that is there more than once, merge the data that goes with it
        for field in MERGABLE_FIELDS:
            indexes = [i for i, f in enumerate(columns) if f == field]
            if len(indexes) <= 1:
                continue
            for line_index, line in enumerate(lines):
                elems = [line[i] for i in indexes]
                merged_data = ' '.join(elems)
                new_line = line[:] # We don't want to touch original lines
                new_line[indexes[0]] = merged_data
                for index_to_remove in reversed(indexes[1:]):
                    del new_line[index_to_remove]
                lines[line_index] = new_line
            for index_to_remove in reversed(indexes[1:]):
                del columns[index_to_remove]

    def _prepare(self, infile):
        # Comment lines can confuse the sniffer. We remove them
        readcontent = infile.read()
        content = readcontent.replace(b'\0', b'').decode('latin-1')
        lines = content.split('\n')
        stripped_lines = [line.strip() for line in lines]
        stripped_lines = [line for line in stripped_lines if line and not line.startswith('#')]
        try:
            self.dialect = csv.Sniffer().sniff('\n'.join(stripped_lines))
        except csv.Error:
            # The sniffer failed, let's manually try a couple of delimiters. We'll first count
            # how many of each delimiter we have per line and we'll use the most popular. Because we
            # don't want to accept something obviously not-CSV as a CSV, we'll have a minimal
            # standard, that is 3 columns. To ensure that, we could say that the mean number of
            # delimiters per line has to be at least 2, but headers and/or footers can have less,
            # do to play on the safe side, we go with 1.5.
            DELIMITERS = set(';,\t|')
            delim2count = {delim: content.count(delim) for delim in DELIMITERS}
            delim, count = max(delim2count.items(), key=lambda x: x[1])
            if count / len(lines) < 1.5:
                raise FileFormatError()

            class ManualDialect(csv.excel):
                delimiter = delim
            self.dialect = ManualDialect
        self.readcontent = readcontent

    def _scan_lines(self, encoding=None):
        if not encoding:
            encoding = 'latin-1'
        content = self.readcontent.decode(encoding, 'ignore').replace('\0', '')
        rawlines = content.splitlines()
        try:
            reader = csv.reader(iter(rawlines), self.dialect)
        except TypeError:
            logging.warning("Invalid Dialect (strangely...). Delimiter: %r", self.dialect.delimiter)
        lines = stripfalse(reader)
        # complete smaller lines and strip whitespaces
        maxlen = max(len(line) for line in lines)
        for line in (l for l in lines if len(l) < maxlen):
            line += [''] * (maxlen - len(line))
        self.lines = lines

    def _parse_date_format(self, lines, ci):
        date_index = ci[CsvField.Date]
        lines_to_load = []
        for line in lines:
            line = line[:]
            cleaned_str_date = base.clean_date(line[date_index])
            if cleaned_str_date is None:
                logging.warning('{0} is not a date. Ignoring line'.format(line[date_index]))
            else:
                line[date_index] = cleaned_str_date
                lines_to_load.append(line)
        del line
        str_dates = [line[date_index] for line in lines_to_load]
        date_format = self.guess_date_format(str_dates)
        if date_format is None:
            raise FileLoadError(tr("The Date column has been set on a column that doesn't contain dates."))
        return date_format, lines_to_load

    def _check_amount_values(self, lines, ci):
        for line in lines:
            for attr in [CsvField.Amount, CsvField.Increase, CsvField.Decrease]:
                if attr not in ci:
                    continue
                index = ci[attr]
                value = line[index]
                try:
                    base.parse_amount(value, self.default_currency)
                except ValueError:
                    raise FileLoadError(tr("The Amount column has been set on a column that doesn't contain amounts."))

    # --- Override
    def _parse(self, infile):
        self._prepare(infile)
        self._scan_lines()

    def _load(self):
        lines = self.lines[:]
        colcount = len(lines[0]) if lines else 0
        columns = self.columns[:colcount]
        self._merge_columns(columns, lines)
        ci = {}
        for index, field in enumerate(columns):
            if field is not None:
                ci[field] = index
        hasdate = CsvField.Date in ci
        hasamount = (CsvField.Amount in ci) or (CsvField.Increase in ci and CsvField.Decrease in ci)
        if not (hasdate and hasamount):
            raise FileLoadError(tr("The Date and Amount columns must be set."))
        target_account = self.accounts.create(
            'CSV Import', self.default_currency, AccountType.Asset)
        self.parsing_date_format, lines_to_load = self._parse_date_format(lines, ci)
        self._check_amount_values(lines_to_load, ci)
        for line in lines_to_load:
            info = base.TransactionInfo()
            info.account = target_account.name
            for attr, index in ci.items():
                value = line[index]
                if attr == CsvField.Date:
                    value = base.parse_date_str(value, self.parsing_date_format)
                elif attr == CsvField.Increase:
                    attr = CsvField.Amount
                elif attr == CsvField.Decrease:
                    attr = CsvField.Amount
                    if value.strip() and not value.startswith('-'):
                        value = '-' + value
                if isinstance(value, str):
                    value = value.strip()
                if value:
                    setattr(info, attr, value)
            if info.is_valid():
                txn = info.load(self.accounts)
                self.transactions.add(txn)

    # --- Public
    def rescan(self, encoding=None):
        self._scan_lines(encoding=encoding)

