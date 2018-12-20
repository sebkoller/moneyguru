PYTHON ?= python

SRCS = currency.c amount.c account.c split.c transaction.c entry.c util.c
OBJS = $(SRCS:%.c=%.o)
TEST_SRCS = $(addprefix tests/, amount.c transaction.c main.c)
TEST_OBJS = $(TEST_SRCS:%.c=%.o)

PY_CC = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CC'))")
BLDSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDSHARED'))")
BLDLIBRARY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDLIBRARY'))")
CFLAGS_PY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CFLAGS'))")
CFLAGSFORSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CFLAGSFORSHARED'))")
INCLUDEPY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))")
SOABI = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('SOABI'))")
PY_CCORE = py_ccore.c
PY_CCORE_OBJ = py_ccore.$(SOABI).o
TARGET = _ccore.$(SOABI).so

DEFAULT_CFLAGS = -std=c99 -Wall $(CFLAGSFORSHARED)
CFLAGS ?= $(DEFAULT_CFLAGS)
LDFLAGS = `pkg-config --libs sqlite3` $(BLDLIBRARY)
LDFLAGS_TEST = `pkg-config --libs cunit sqlite3` -lm

.PHONY: all
all: $(TARGET)

$(TARGET): $(OBJS) $(PY_CCORE_OBJ)
	$(BLDSHARED) $^ $(LDFLAGS) -o $@

$(PY_CCORE_OBJ): $(PY_CCORE)
	$(PY_CC) -c $(CFLAGS) $(CFLAGS_PY) -I$(INCLUDEPY) -o $@ $^

runtests: $(TEST_OBJS) $(OBJS)
	$(CC) $^ $(LDFLAGS_TEST) -o $@

.PHONY: tests
tests: runtests
	./runtests

.PHONY: clean
clean:
	-rm -f $(OBJS) $(PY_CCORE_OBJ) $(TARGET) $(TEST_OBJS) runtests

