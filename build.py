# Copyright 2018 Virgil Dupras
#
# This software is licensed under the "GPLv3" License as described in the "LICENSE" file,
# which should be included with this package. The terms are also available at
# http://www.gnu.org/licenses/gpl-3.0.html

import os
import os.path as op
import shutil
from argparse import ArgumentParser
import platform

from setuptools import setup, Extension

from hscommon import sphinxgen
from hscommon.plat import ISLINUX, ISWINDOWS
from hscommon.build import (
    print_and_do, move_all, copy, filereplace
)
from hscommon import loc

def parse_args():
    parser = ArgumentParser()
    parser.add_argument(
        '--dev', action='store_true', default=False,
        help="If this flag is set, will configure for dev builds."
    )
    parser.add_argument(
        '--clean', action='store_true', dest='clean',
        help="Clean build folder before building"
    )
    parser.add_argument(
        '--doc', action='store_true', dest='doc',
        help="Build only the help file"
    )
    parser.add_argument(
        '--loc', action='store_true', dest='loc',
        help="Build only localization"
    )
    parser.add_argument(
        '--updatepot', action='store_true', dest='updatepot',
        help="Generate .pot files from source code."
    )
    parser.add_argument(
        '--mergepot', action='store_true', dest='mergepot',
        help="Update all .po files based on .pot files."
    )
    parser.add_argument(
        '--ext', action='store_true', dest='ext',
        help="Build only ext modules"
    )
    parser.add_argument(
        '--no-ext', action='store_true', dest='no_ext',
        help="Do not build ext modules."
    )
    parser.add_argument(
        '--normpo', action='store_true', dest='normpo',
        help="Normalize all PO files (do this before commit)."
    )
    args = parser.parse_args()
    return args

def clean():
    TOCLEAN = [
        'build',
        op.join('cocoa', 'build'),
        op.join('cocoa', 'autogen'),
        'dist',
        'install',
        op.join('help', 'en', 'image')
    ]
    for path in TOCLEAN:
        try:
            os.remove(path)
        except Exception:
            try:
                shutil.rmtree(path)
            except Exception:
                pass

def build_qt(dev):
    qrc_path = op.join('qt', 'mg.qrc')
    pyrc_path = op.join('qt', 'mg_rc.py')
    ret = print_and_do("pyrcc5 {} > {}".format(qrc_path, pyrc_path))
    if ret != 0:
        raise RuntimeError("pyrcc5 call failed with code {}. Aborting build".format(ret))
    build_help()

def build_help():
    print("Generating Help")
    current_path = op.abspath('.')
    help_basepath = op.join(current_path, 'help', 'en')
    help_destpath = op.join(current_path, 'build', 'help')
    changelog_path = op.join(current_path, 'help', 'changelog')
    credits_path = op.join(current_path, 'help', 'credits.rst')
    credits_tmpl = op.join(help_basepath, 'credits.tmpl')
    credits_out = op.join(help_basepath, 'credits.rst')
    filereplace(credits_tmpl, credits_out, credits=open(credits_path, 'rt', encoding='utf-8').read())
    tixurl = "https://github.com/hsoft/moneyguru/issues/{}"
    sphinxgen.gen(help_basepath, help_destpath, changelog_path, tixurl, None, None)

def build_base_localizations():
    loc.compile_all_po('locale')

def build_qt_localizations():
    loc.compile_all_po(op.join('qtlib', 'locale'))
    loc.merge_locale_dir(op.join('qtlib', 'locale'), 'locale')

def build_localizations():
    build_base_localizations()
    build_qt_localizations()
    locale_dest = op.join('build', 'locale')
    if op.exists(locale_dest):
        shutil.rmtree(locale_dest)
    shutil.copytree('locale', locale_dest, ignore=shutil.ignore_patterns('*.po', '*.pot'))
    if not ISLINUX:
        print("Copying qt_*.qm files into the 'locale' folder")
        from PyQt5.QtCore import QLibraryInfo
        trfolder = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
        for lang in loc.get_langs('locale'):
            qmname = 'qt_%s.qm' % lang
            src = op.join(trfolder, qmname)
            if op.exists(src):
                copy(src, op.join('build', 'locale', qmname))

def build_updatepot():
    print("Building .pot files from source files")
    print("Building core.pot")
    loc.generate_pot(['core'], op.join('locale', 'core.pot'), ['tr'])
    print("Building ui.pot")
    loc.generate_pot(['qt'], op.join('locale', 'ui.pot'), ['tr'])
    print("Building qtlib.pot")
    loc.generate_pot(['qtlib'], op.join('qtlib', 'locale', 'qtlib.pot'), ['tr'])

def build_mergepot():
    print("Updating .po files using .pot files")
    loc.merge_pots_into_pos('locale')
    loc.merge_pots_into_pos(op.join('qtlib', 'locale'))

def build_normpo():
    loc.normalize_all_pos('locale')
    loc.normalize_all_pos(op.join('qtlib', 'locale'))
    loc.normalize_all_pos(op.join('cocoalib', 'locale'))

def build_ext():
    print("Building C extensions")
    if ISWINDOWS and platform.architecture()[0] == '64bit':
        print("""Detecting a 64bit Windows here. You might have problems compiling. If you do, do this:
1. Install the Windows SDK.
2. Start the Windows SDK's console.
3. Then run:
setenv /x64 /release
set DISTUTILS_USE_SDK=1
set MSSdk=1
4. Try the build command again.
If the above fails and you are testing locally for a non-production release,
then you can pass a --no-ext option to this build script to skip the extension
module which will then use pure python reference implementations.
        """)
    exts = []
    exts.append(Extension(
        '_amount',
        [op.join('core', 'modules', 'amount.c')],
        # Needed to avoid tricky compile warnings after having enabled the strict ABI
        extra_compile_args=['-fno-strict-aliasing'],
    ))
    setup(
        script_args=['build_ext', '--inplace'],
        ext_modules=exts,
    )
    move_all('_amount*', op.join('core', 'model'))

def build_normal(dev, do_build_ext=True):
    build_localizations()
    if do_build_ext:
        build_ext()
    build_qt(dev)

def main():
    args = parse_args()
    print("Building moneyGuru")
    if args.dev:
        print("Building in Dev mode")
    if args.clean:
        clean()
    if not op.exists('build'):
        os.mkdir('build')
    if args.doc:
        build_help()
    elif args.loc:
        build_localizations()
    elif args.updatepot:
        build_updatepot()
    elif args.mergepot:
        build_mergepot()
    elif args.normpo:
        build_normpo()
    elif args.ext:
        build_ext()
    else:
        build_normal(args.dev, not args.no_ext)

if __name__ == '__main__':
    main()

