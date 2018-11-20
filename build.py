# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os.path as op
from argparse import ArgumentParser

from hscommon import loc

def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '--mergepot', action='store_true', dest='mergepot',
        help="Update all .po files based on .pot files."
    )
    parser.add_argument(
        '--normpo', action='store_true', dest='normpo',
        help="Normalize all PO files (do this before commit)."
    )
    args = parser.parse_args()
    return args

def build_mergepot():
    print("Updating .po files using .pot files")
    loc.merge_pots_into_pos('locale')
    loc.merge_pots_into_pos(op.join('qtlib', 'locale'))

def build_normpo():
    loc.normalize_all_pos('locale')
    loc.normalize_all_pos(op.join('qtlib', 'locale'))
    loc.normalize_all_pos(op.join('cocoalib', 'locale'))

def main():
    args = parse_args()
    if args.mergepot:
        build_mergepot()
    elif args.mergepot:
        build_mergepot()

if __name__ == '__main__':
    main()

