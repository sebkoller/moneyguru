PYTHON ?= python3
SHEBANG ?= /usr/bin/env $(PYTHON)
REQ_MINOR_VERSION = 4
PREFIX ?= /usr/local
DESTLIB ?= $(PREFIX)/lib/moneyguru
DESTSHARE ?= $(PREFIX)/share/moneyguru
DESTDOC ?= $(PREFIX)/share/doc/moneyguru

SOABI = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('SOABI'))")
CCORE_NAME = _ccore.$(SOABI).so
CCORE_SRC = ccore/$(CCORE_NAME)
CCORE_DEST = core/model/$(CCORE_NAME)

# If you're installing into a path that is not going to be the final path prefix (such as a
# sandbox), set DESTDIR to that path.

localedirs = $(wildcard locale/*/LC_MESSAGES)
pofiles = $(wildcard locale/*/LC_MESSAGES/*.po)
mofiles = $(patsubst %.po,%.mo,$(pofiles))

vpath %.po $(localedirs)
vpath %.mo $(localedirs)

all: qt/mg_rc.py run.py $(CCORE_DEST) | i18n reqs
	@echo "Build complete! You can run moneyGuru with 'make run'"

run:
	./run.py

pyc:
	${PYTHON} -m compileall core qt

reqs:
	@ret=`${PYTHON} -c "import sys; print(int(sys.version_info[:2] >= (3, ${REQ_MINOR_VERSION})))"`; \
		if [ $${ret} -ne 1 ]; then \
			echo "Python 3.${REQ_MINOR_VERSION}+ required. Aborting."; \
			exit 1; \
		fi
	@${PYTHON} -c 'import PyQt5' >/dev/null 2>&1 || \
		{ echo "PyQt 5.4+ required. Install it and try again. Aborting"; exit 1; }

help/%/changelog.rst: help/%/changelog.head.rst help/changelog 
	$(PYTHON) support/genchangelog.py help/changelog | cat $< - > $@

help/%/credits.rst: help/%/credits.head.rst help/credits.rst 
	cat $+ > $@

build/help/%: help/% help/%/changelog.rst help/%/credits.rst
	$(PYTHON) -m sphinx $< $@

alldocs: $(addprefix build/help/,en cs de fr it ru)

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

$(CCORE_SRC):
	$(MAKE) -C ccore

$(CCORE_DEST): $(CCORE_SRC)
	cp $^ $@

ccore: $(CCORE_DEST)

mergepot:
	./support/mergepot.sh

normpo:
	find locale -name *.po -exec msgcat {} -o {} \;

srcpkg:
	./support/srcpkg.sh

install: all pyc
	./support/install.sh "$(DESTDIR)" "$(PREFIX)" "$(DESTLIB)" "$(DESTSHARE)"

installdocs: build/help/en
	mkdir -p $(DESTDIR)$(DESTDOC)
	cp -rf $^/* $(DESTDIR)$(DESTDOC)

clean:
	$(MAKE) -C ccore clean
	-rm -rf build
	find locale -name *.mo -delete
	-rm -f core/model/*.so
	-rm -f run.py
	-rm -f qt/mg_rc.py

.PHONY : clean srcpkg normpo mergepot ccore i18n reqs run pyc install all alldocs
