# moneyGuru

[![Build Status](https://travis-ci.org/hsoft/moneyguru.svg?branch=master)](https://travis-ci.org/hsoft/moneyguru)

[moneyGuru][moneyguru] is a personal finance management application. With it,
you can evaluate your financial situation so you can make informed (and thus
better) decisions. Most finance applications have the same goal, but
moneyGuru's difference is in the way it achieves it. Rather than having reports
which you have to configure (or find out which pre-configured report is the
right one), your important financial data (net worth, profit) is constantly
up-to-date and "in your face". This allows you to constantly make informed
decision rather than doing so periodically.

# Current status: People wanted

moneyGuru has currently only one maintainer, me. This is a dangerous situation
that needs to be corrected.

The goal is to eventually have another active maintainer, but before we can get
there, the project needs more contributors.

Whatever your skills, if you are remotely interestested in being a contributor,
I'm interested in mentoring you. If that's the case, please refer to [the open
ticket on the subject][contrib-issue] and let's get started.

## Windows? Mac OS? gone

moneyGuru used to run on Windows and Mac OS, but I haven't had a Windows or
MacOS setup in years, I can't (and don't want to) produce builds for these
targets any more.

I don't purposefully remove platform-agnostic mechanics, but when they stand in
my way, I scrap them (can't test? worthless code) and I've been doing that for
a while now. As a result, this app pretty much became a GNU/Linux app.

There have been unsuccessful attempts from some people in the past to pick these
platforms up. Didn't work. The challenge becomes greater as time passes.

Still, if you're interested in reviving a platform, go ahead. If you get far
enough, I'll be delighted to point to your builds as the official ones. I'll
also be glad to reinstate platform-agnostic mechanics in the core code.

What used to be the Cocoa UI of moneyGuru is hosted in a separate repo:
https://github.com/hsoft/moneyguru-cocoa

The Windows version used Qt, so it didn't have a separate UI codebase.

# Contents of this folder

This package contains the source for moneyGuru. Its documentation is
[available online][documentation]. Here's how this source tree is organised:

* ccore: The "very core" code of moneyGuru. Written in C. Introduced recently,
         will expand with time. The goal could be to rewrite the whole of `core`
         in C, but `core.gui` will be a big chunk. Might not be worth it.
* core: Contains the core logic code for moneyGuru. It's Python code.
* qt: UI code for the Qt toolkit. It's written in Python and uses PyQt.
* images: Images used by the different UI codebases.
* help: Help document, written for [Sphinx][sphinx].
* locale: .po files for localisation.
* support: various files to help with the build process.

There are also other sub-folder that comes from external repositories and are
part of this repo as git submodules:

* hscommon: A collection of helpers used across HS applications.
* qtlib: A collection of helpers used across Qt UI codebases of HS applications.

# How to build moneyGuru from source

### Prerequisites

* Python 3.4+
* PyQt5
* GNU build environment

On Ubuntu, the apt-get command to install all pre-requisites is:

    $ apt-get install python3-dev python3-pyqt5 pyqt5-dev-tools

On Arch, it's:

    $ pacman -S python-pyqt5

On Gentoo, it's:

    $ USE="gui widgets printsupport" emerge PyQt5

### make

moneyGuru is built with "make":

    $ make
    $ make run

# Running tests

The complete test suite is ran with [Tox 1.7+][tox]. If you have it installed
system-wide, you don't even need to set up a virtualenv. Just `cd` into the
root project folder and run `tox`.

If you don't have Tox system-wide, install it in your virtualenv with `pip
install tox` and then run `tox`.

You can also run automated tests without Tox. Extra requirements for running
tests are in `requirements-tests.txt`. So, you can do `pip install -r
requirements-tests.txt` inside your virtualenv and then `py.test core hscommon`

# Further documentation

For further development-related documentation, there's a "moneyGuru Developer
Documentation" section in the english version of the main documentation. This
documentation is built with the app and is also [available
online][documentation].

[moneyguru]: http://www.hardcoded.net/moneyguru/
[documentation]: http://www.hardcoded.net/moneyguru/help/en/
[contrib-issue]: https://github.com/hsoft/moneyguru/issues/425
[pyqt]: http://www.riverbankcomputing.com
[sphinx]: http://sphinx.pocoo.org/
[tox]: https://tox.readthedocs.org/en/latest/

