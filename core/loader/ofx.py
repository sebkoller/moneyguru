# Copyright 2019 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html
#
# Sections refer to the OFX 1.0.3 spec.

from itertools import dropwhile

from ..exception import FileFormatError
from .sgmllib import SGMLParser
from . import base

class OFXParser(SGMLParser):
    def __init__(self, loader, accounts_only=False):
        super().__init__()
        self.loader = loader
        self.data = ''
        self.data_handler = None
        self.accounts_only = accounts_only

    # --- Helper methods

    def flush_data(self):
        if self.data_handler:
            self.data_handler(self.data.strip())
            self.data_handler = None
        self.data = ''

    # --- Global hooks

    def handle_starttag(self, tag, method, attributes):
        self.flush_data()
        super().handle_starttag(tag, method, attributes)

    def handle_endtag(self, tag, method):
        self.flush_data()
        super().handle_endtag(tag, method)

    def unknown_starttag(self, tag, attributes):
        self.flush_data()

    def unknown_endtag(self, tag):
        self.flush_data()

    def handle_data(self, data):
        self.data += data

    # --- Account tags

    def start_stmtrs(self, attributes):
        self.loader.start_account()
        self.account_info = self.loader.account_info
    start_ccstmtrs = start_stmtrs

    def end_stmtrs(self):
        a = self.account_info
        if hasattr(a, 'ofx_bank_id') and hasattr(a, 'ofx_acct_id'):
            ofx_branch_id = getattr(a, 'ofx_branch_id', '')
            a.reference = '|'.join([a.ofx_bank_id, ofx_branch_id, a.ofx_acct_id])
        self.loader.flush_account()

    def start_curdef(self, attributes):
        self.data_handler = self.handle_curdef

    def handle_curdef(self, data):
        self.account_info.currency = data

    def start_bankid(self, attributes):
        self.data_handler = self.handle_bankid

    def handle_bankid(self, data):
        self.account_info.ofx_bank_id = data

    def start_branchid(self, attributes):
        self.data_handler = self.handle_branchid

    def handle_branchid(self, data):
        self.account_info.ofx_branch_id = data

    def start_acctid(self, attributes):
        self.data_handler = self.handle_acctid

    def handle_acctid(self, data):
        self.account_info.ofx_acct_id = data
        self.account_info.name = data

    # --- Entry tags

    def start_stmttrn(self, attributes):
        if self.accounts_only:
            return
        self.loader.start_transaction()
        self.transaction_info = self.loader.transaction_info

    def end_stmttrn(self):
        if self.accounts_only:
            return
        self.loader.flush_transaction()

    def start_fitid(self, attributes):
        self.data_handler = self.handle_fitid

    def handle_fitid(self, data):
        if self.accounts_only:
            return
        self.transaction_info.reference = data

    def start_name(self, attributes):
        self.data_handler = self.handle_name

    def handle_name(self, data):
        if self.accounts_only:
            return
        self.transaction_info.description = data

    def start_dtposted(self, attributes):
        self.data_handler = self.handle_dtposted

    def handle_dtposted(self, data):
        if self.accounts_only:
            return
        self.transaction_info.date = self.loader.parse_date_str(data[:8])

    def start_trnamt(self, attributes):
        self.data_handler = self.handle_trnamt

    def handle_trnamt(self, data):
        if self.accounts_only:
            return
        self.transaction_info.amount = data


class Loader(base.Loader):
    FILE_ENCODING = 'cp1252'
    NATIVE_DATE_FORMAT = '%Y%m%d'

    # --- Override
    def _parse(self, infile):
        # First line is OFXHEADER (section 2.2.1)
        line = '\n'
        while line and not line.strip(): # skip the first lines if they're blank
            line = infile.readline()
        line = line.strip()
        if line != 'OFXHEADER:100' and not line.startswith('<?OFX'):
            raise FileFormatError()
        self.lines = list(infile)

    def _load(self):
        is_header = lambda line: not line.startswith('<')
        parser = OFXParser(self, accounts_only=True)
        for line in dropwhile(is_header, self.lines):
            parser.feed(line)
        parser.close()
        parser = OFXParser(self)
        for line in dropwhile(is_header, self.lines):
            parser.feed(line)
        parser.close()

