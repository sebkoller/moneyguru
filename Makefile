PYTHON ?= python3
SHEBANG ?= /usr/bin/env $(PYTHON)
REQ_MINOR_VERSION = 4
PREFIX ?= /usr/local

# If you're installing into a path that is not going to be the final path prefix (such as a
# sandbox), set DESTDIR to that path.

# Our build scripts are not very "make like" yet and perform their task in a bundle. For now, we
# use one of each file to act as a representative, a target, of these groups.
submodules_target = hscommon/__init__.py

packages = hscommon core qt
localedirs = $(wildcard locale/*/LC_MESSAGES)
pofiles = $(wildcard locale/*/LC_MESSAGES/*.po)
mofiles = $(patsubst %.po,%.mo,$(pofiles))

vpath %.po $(localedirs)
vpath %.mo $(localedirs)

all: qt/mg_rc.py run.py | i18n ccore $(submodules_target) reqs
	@echo "Build complete! You can run moneyGuru with 'make run'"

run:
	./run.py

pyc:
	${PYTHON} -m compileall ${packages}

reqs:
	@ret=`${PYTHON} -c "import sys; print(int(sys.version_info[:2] >= (3, ${REQ_MINOR_VERSION})))"`; \
		if [ $${ret} -ne 1 ]; then \
			echo "Python 3.${REQ_MINOR_VERSION}+ required. Aborting."; \
			exit 1; \
		fi
	@${PYTHON} -c 'import PyQt5' >/dev/null 2>&1 || \
		{ echo "PyQt 5.4+ required. Install it and try again. Aborting"; exit 1; }

# Ensure that submodules are initialized
$(submodules_target):
	git submodule init
	git submodule update

help/en/changelog.rst: help/changelog help/en/changelog.head.rst
	$(PYTHON) support/genchangelog.py help/changelog | cat help/en/changelog.head.rst - > $@

help/en/credits.rst: help/en/credits.head.rst help/credits.rst 
	cat $+ > $@

build/help: help/en/changelog.rst help/en/credits.rst
	$(PYTHON) -m sphinx help/en $@

qt/mg_rc.py : qt/mg.qrc
	pyrcc5 $< > $@

run.py: support/run.template.py
	sed -e 's|@SHEBANG@|#!$(SHEBANG)|' $< > $@
	chmod +x $@

i18n: $(mofiles)

%.mo : %.po
	msgfmt -o $@ $<	

ccore:
	make -C ccore PYTHON=$(PYTHON)
	cp ccore/_ccore.so core/model

mergepot:
	./support/mergepot.sh

normpo:
	find locale -name *.po -exec msgcat {} -o {} \;

srcpkg:
	./support/srcpkg.sh

install: all pyc
	mkdir -p ${DESTDIR}${PREFIX}/share/moneyguru
	cp -rf ${packages} locale ${DESTDIR}${PREFIX}/share/moneyguru
	cp -f run.py ${DESTDIR}${PREFIX}/share/moneyguru/run.py
	chmod 755 ${DESTDIR}${PREFIX}/share/moneyguru/run.py
	mkdir -p ${DESTDIR}${PREFIX}/bin
	ln -sf ${PREFIX}/share/moneyguru/run.py ${DESTDIR}${PREFIX}/bin/moneyguru
	mkdir -p ${DESTDIR}${PREFIX}/share/applications
	cp -f share/moneyguru.desktop ${DESTDIR}${PREFIX}/share/applications
	sed -i -e 's#^Icon=/usr/share/moneyguru/#Icon='${PREFIX}'/share/moneyguru/#' \
		${DESTDIR}${PREFIX}/share/applications/moneyguru.desktop
	mkdir -p ${DESTDIR}${PREFIX}/share/pixmaps
	cp -f images/logo_big.png ${DESTDIR}${PREFIX}/share/pixmaps/moneyguru.png
	cp -f images/logo_big.png ${DESTDIR}${PREFIX}/share/moneyguru/logo_big.png

installdocs: build/help
	mkdir -p ${DESTDIR}${PREFIX}/share/moneyguru
	cp -rf build/help ${DESTDIR}${PREFIX}/share/moneyguru

uninstall :
	rm -rf "${DESTDIR}${PREFIX}/share/moneyguru"
	rm -f "${DESTDIR}${PREFIX}/bin/moneyguru"
	rm -f "${DESTDIR}${PREFIX}/share/applications/moneyguru.desktop"
	rm -f "${DESTDIR}${PREFIX}/share/pixmaps/moneyguru.png"

clean:
	make -C ccore clean
	-rm -rf build env
	-rm -rf locale/*/LC_MESSAGES/*.mo
	-rm -rf core/model/*.so
	-rm -rf run.py

.PHONY : clean srcpkg normpo mergepot ccore i18n reqs run pyc install uninstall all
