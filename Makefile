PYTHON ?= python3
SHEBANG ?= /usr/bin/env $(PYTHON)
REQ_MINOR_VERSION = 4
PREFIX ?= /usr/local
DESTSHARE = $(DESTDIR)$(PREFIX)/share/moneyguru

# If you're installing into a path that is not going to be the final path prefix (such as a
# sandbox), set DESTDIR to that path.

packages = hscommon core qt
localedirs = $(wildcard locale/*/LC_MESSAGES)
pofiles = $(wildcard locale/*/LC_MESSAGES/*.po)
mofiles = $(patsubst %.po,%.mo,$(pofiles))

vpath %.po $(localedirs)
vpath %.mo $(localedirs)

all: qt/mg_rc.py run.py | i18n ccore reqs
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
	install -D run.py $(DESTSHARE)/run.py
	mkdir -p ${DESTDIR}${PREFIX}/bin
	ln -sf $(DESTSHARE)/run.py ${DESTDIR}${PREFIX}/bin/moneyguru
	cp -rf ${packages} $(DESTSHARE)
	mkdir -p ${DESTDIR}${PREFIX}/share/applications
	install -D -m644 support/moneyguru.desktop \
		${DESTDIR}${PREFIX}/share/applications/moneyguru.desktop
	sed -i -e 's#^Icon=/usr/share/moneyguru/#Icon='${PREFIX}'/share/moneyguru/#' \
		${DESTDIR}${PREFIX}/share/applications/moneyguru.desktop
	install -D -m644 images/logo_big.png \
		${DESTDIR}${PREFIX}/share/pixmaps/moneyguru.png
	install -m644 images/logo_big.png $(DESTSHARE)/logo_big.png
	find locale -name *.mo -exec install -D {} $(DESTSHARE)/{} \;

installdocs: build/help
	mkdir -p $(DESTSHARE)
	cp -rf build/help $(DESTSHARE)

uninstall :
	rm -rf "${DESTDIR}${PREFIX}/share/moneyguru"
	rm -f "${DESTDIR}${PREFIX}/bin/moneyguru"
	rm -f "${DESTDIR}${PREFIX}/share/applications/moneyguru.desktop"
	rm -f "${DESTDIR}${PREFIX}/share/pixmaps/moneyguru.png"

clean:
	$(MAKE) -C ccore clean
	-rm -rf build env
	-rm -rf locale/*/LC_MESSAGES/*.mo
	-rm -rf core/model/*.so
	-rm -rf run.py

.PHONY : clean srcpkg normpo mergepot ccore i18n reqs run pyc install uninstall all
