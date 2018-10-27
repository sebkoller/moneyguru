PYTHON ?= python3
REQ_MINOR_VERSION = 4
PREFIX ?= /usr/local

# Set this variable if all dependencies are already met on the system. We will then avoid the
# whole vitualenv creation and pip install dance.
NO_VENV ?=
UBUNTU_VERSION ?= xenial

ifdef NO_VENV
	VENV_PYTHON = $(PYTHON)
else
	VENV_PYTHON = ./env/bin/python
endif

# If you're installing into a path that is not going to be the final path prefix (such as a
# sandbox), set DESTDIR to that path.

# Our build scripts are not very "make like" yet and perform their task in a bundle. For now, we
# use one of each file to act as a representative, a target, of these groups.
submodules_target = hscommon/__init__.py

packages = hscommon qtlib core qt
localedirs = $(wildcard locale/*/LC_MESSAGES)
pofiles = $(wildcard locale/*/LC_MESSAGES/*.po)
mofiles = $(patsubst %.po,%.mo,$(pofiles))

vpath %.po $(localedirs)
vpath %.mo $(localedirs)

all : | env i18n modules qt/mg_rc.py
	@echo "Build complete! You can run moneyGuru with 'make run'"

run:
	$(VENV_PYTHON) run.py

pyc:
	${PYTHON} -m compileall ${packages}

reqs :
	@ret=`${PYTHON} -c "import sys; print(int(sys.version_info[:2] >= (3, ${REQ_MINOR_VERSION})))"`; \
		if [ $${ret} -ne 1 ]; then \
			echo "Python 3.${REQ_MINOR_VERSION}+ required. Aborting."; \
			exit 1; \
		fi
ifndef NO_VENV
	@${PYTHON} -m venv -h > /dev/null || \
		echo "Creation of our virtualenv failed. If you're on Ubuntu, you probably need python3-venv."
endif
	@${PYTHON} -c 'import PyQt5' >/dev/null 2>&1 || \
		{ echo "PyQt 5.4+ required. Install it and try again. Aborting"; exit 1; }

# Ensure that submodules are initialized
$(submodules_target) :
	git submodule init
	git submodule update

env : | $(submodules_target) reqs
ifndef NO_VENV
	@echo "Creating our virtualenv"
	${PYTHON} -m venv env
	$(VENV_PYTHON) -m pip install -r requirements.txt
# We can't use the "--system-site-packages" flag on creation because otherwise we end up with
# the system's pip and that messes up things in some cases (notably in Gentoo).
	${PYTHON} -m venv --upgrade --system-site-packages env
endif

help/en/changelog.rst: help/changelog help/en/changelog.head.rst
	$(PYTHON) scripts/genchangelog.py help/changelog | cat help/en/changelog.head.rst - > $@

help/en/credits.rst: help/credits.rst help/en/credits.head.rst
	cat help/en/credits.head.rst help/credits.rst > $@

build/help : help/en/changelog.rst help/en/credits.rst | env
ifndef NO_VENV
	$(VENV_PYTHON) -m pip install -r requirements-docs.txt
endif
	$(VENV_PYTHON) -m sphinx help/en $@

qt/mg_rc.py : qt/mg.qrc
	pyrcc5 qt/mg.qrc > qt/mg_rc.py

i18n: $(mofiles)

%.mo : %.po
	msgfmt -o $@ $<	

core/model/_amount.*.so : core/modules/amount.c | env
	$(VENV_PYTHON) hscommon/build_ext.py $^ _amount
	mv _amount.*.so core/model

modules : core/model/_amount.*.so

mergepot :
	$(VENV_PYTHON) build.py --mergepot

normpo :
	$(VENV_PYTHON) build.py --normpo

srcpkg :
	./scripts/srcpkg.sh

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
	-rm -rf build
	-rm locale/*/LC_MESSAGES/*.mo
	-rm core/model/*.so

.PHONY : clean srcpkg normpo mergepot modules i18n reqs run pyc install uninstall all
