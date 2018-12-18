PYTHON ?= python
TARGET = _ccore.so

SRCS = currency.c amount.c account.c split.c transaction.c util.c py_ccore.c
OBJS = $(SRCS:%.c=%.o)

CC = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CC'))")
BLDSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDSHARED'))")
BLDLIBRARY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDLIBRARY'))")
CFLAGS_PY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CFLAGS'))")
CFLAGSFORSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CFLAGSFORSHARED'))")
INCLUDEPY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))")
DEFAULT_CFLAGS = -std=c99 $(CFLAGS_PY) $(CFLAGSFORSHARED) -I$(INCLUDEPY)
CFLAGS ?= $(DEFAULT_CFLAGS)
LDFLAGS = `pkg-config --libs sqlite3` $(BLDLIBRARY)

.PHONY: all
all: $(TARGET)

$(TARGET): $(OBJS)
	$(BLDSHARED) $^ $(LDFLAGS) -o $@

.PHONY: clean
clean:
	-rm -rf $(OBJS) $(TARGET) $(EXECUTABLE)

