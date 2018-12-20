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

# The great C rewrite

If you look at recent commits in this project, you'll notice that there a
**lot** of activity to rewrite Python code in C. Yup, that's what I'm doing.
The long term goal would be to rewrite the entirety of `core` in C, keeping
only the Python test suite. That would be a huge effort though. `core.gui`,
`core.document` are too big and dynamic. I don't think I'll actually get there.
`core.model`, `core.loader` and `core.saver` are more realistic goals.

Why am I doing this? Mostly because I'm aching to become more intimate with C.
Sure, I already know C a little bit, did toy projects, participated to other
established ones, but I don't feel like I'm proficient in C. I don't know what
it takes to build a "real C app" with everything it entails (proper build
system, using glibc, really have to deal with memory management problems, using
well known libraries (sqlite and soon icu), internalizing pointer logic (I know
how pointers work, but it's not natural for my brain to think about pointer
logic))

In almost any case, if you're telling me "I'm planning on rewriting this 50K
SLOC python app", I'm going to tell you "you're crazy, it's a guaranteed
failure".

However, 10 years ago when I insisted on strict TDD with all tests being at the
integration testing level, that costed me a lot of efforts that ended up being
a bit useless, considering the limited success of the application.

It occurred to me recently that the result of that effort was a great untapped
asset because it *does* allow the kind of rewrite that in any other situation
would be a guaranteed failure: test coverage on moneyGuru is very good and is
written at a level that allows everything underneath to take pretty much any
form.

Those tests are like a teacher telling me "you're doing it (wrong|right)". If
tests pass without segfaults, it has pretty good chances of being sound code
because many many cases are covered. That allows me to try a lot of thing. The
only uncaught problem is memory leaks. I'll have to learn using tools to detect
them soon.

If moneyGuru had other developers around it, I wouldn't do it because it would
be rather rude to them, but since I'm pretty much alone with this project, I'm
paying myself a learning lesson. 

Users shouldn't suffer much from the rewrite: test coverage is very good and I
still use this app for my own personal needs, so it's not going to end up with
glaring post-rewrite problems. Users *will*, on the other hand, benefit from
decreased resource usage and increased speed.

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

## Prerequisites

* [CUnit][cunit]
* [Tox][tox]

## Running

The complete test suite is ran with Tox. `cd` into the project folder and run
`tox`.

You can also run automated tests without Tox but you'll need to install
[pytest][pytest] 3.10+. You can then run `pytest core`

There are some C-only tests that run with Cunit. Tox already runs them, but if
you want to run them as well, you can `cd` into `ccore` and run `make tests`.

# Further documentation

For further development-related documentation, there's a "moneyGuru Developer
Documentation" section in the english version of the main documentation. This
documentation is built with the app and is also [available
online][documentation].

[moneyguru]: http://www.hardcoded.net/moneyguru/
[documentation]: http://www.hardcoded.net/moneyguru/help/en/
[contrib-issue]: https://github.com/hsoft/moneyguru/issues/425
[tox]: https://tox.readthedocs.org/en/latest/
[cunit]: http://cunit.sourceforge.net/
[pytest]: https://pytest.org

