PYTHON ?= python3
SHEBANG ?= /usr/bin/env $(PYTHON)
REQ_MINOR_VERSION = 4
PREFIX ?= /usr/local
DESTLIB ?= $(PREFIX)/lib/moneyguru
DESTSHARE ?= $(PREFIX)/share/moneyguru
DESTDOC ?= $(PREFIX)/share/doc/moneyguru
CCORE = core/model/_ccore.so

# If you're installing into a path that is not going to be the final path prefix (such as a
# sandbox), set DESTDIR to that path.

localedirs = $(wildcard locale/*/LC_MESSAGES)
pofiles = $(wildcard locale/*/LC_MESSAGES/*.po)
mofiles = $(patsubst %.po,%.mo,$(pofiles))

vpath %.po $(localedirs)
vpath %.mo $(localedirs)

all: qt/mg_rc.py run.py $(CCORE) | i18n reqs
	@echo "Build complete! You can run moneyGuru with 'make run'"

run:
	./run.py

pyc:
	${PYTHON} -m compileall hscommon core qt

reqs:
	@ret=`${PYTHON} -c "import sys; print(int(sys.version_info[:2] >= (3, ${REQ_MINOR_VERSION})))"`; \
		if [ $${ret} -ne 1 ]; then \
			echo "Python 3.${REQ_MINOR_VERSION}+ required. Aborting."; \
			exit 1; \
		fi
	@${PYTHON} -c 'import PyQt5' >/dev/null 2>&1 || \
		{ echo "PyQt 5.4+ required. Install it and try again. Aborting"; exit 1; }

help/en/changelog.rst: help/changelog help/en/changelog.head.rst
	$(PYTHON) support/genchangelog.py help/changelog | cat help/en/changelog.head.rst - > $@

help/en/credits.rst: help/en/credits.head.rst help/credits.rst 
	cat $+ > $@

build/help: help/en/changelog.rst help/en/credits.rst
	$(PYTHON) -m sphinx help/en $@

qt/mg_rc.py : qt/mg.qrc
	pyrcc5 $< > $@

run.py: support/run.template.py
	sed -e 's|@SHEBANG@|#!$(SHEBANG)|' \
		-e 's|@SHAREPATH@|$(DESTSHARE)|' \
		-e 's|@DOCPATH@|$(DESTDOC)|' \
		$< > $@
	chmod +x $@

i18n: $(mofiles)

%.mo : %.po
	msgfmt -o $@ $<	

$(CCORE):
	$(MAKE) -C ccore
	cp ccore/_ccore.so core/model

ccore: 
	$(MAKE) -C ccore
	cp ccore/_ccore.so core/model
	# don't leave .o that might be incompatible with the version of python it's
	# going to be built for next (for example, with tox runs).
	# TODO: don't require clean to avoid python ABI mismatch.
	$(MAKE) -C ccore clean

mergepot:
	./support/mergepot.sh

normpo:
	find locale -name *.po -exec msgcat {} -o {} \;

srcpkg:
	./support/srcpkg.sh

install: all pyc
	./support/install.sh "$(DESTDIR)" "$(PREFIX)" "$(DESTLIB)" "$(DESTSHARE)"

installdocs: build/help
	mkdir -p $(DESTDIR)$(DESTDOC)
	cp -rf $^/* $(DESTDIR)$(DESTDOC)

clean:
	$(MAKE) -C ccore clean
	-rm -rf build
	find locale -name *.mo -delete
	-rm -f core/model/*.so
	-rm -f run.py

.PHONY : clean srcpkg normpo mergepot ccore i18n reqs run pyc install uninstall all
