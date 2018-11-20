PYTHON ?= python
TARGET = _ccore.so

PY_SRCS = py_currency.c py_amount.c py_ccore.c
SRCS = currency.c amount.c $(PY_SRCS)
OBJS = $(SRCS:%.c=%.o)

CC = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CC'))")
BLDSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDSHARED'))")
BLDLIBRARY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('BLDLIBRARY'))")
CFLAGSFORSHARED = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('CFLAGSFORSHARED'))")
INCLUDEPY = $(shell $(PYTHON) -c "import sysconfig; print(sysconfig.get_config_var('INCLUDEPY'))")
CFLAGS ?=
CFLAGS += -std=c99 $(CFLAGSFORSHARED) -I$(INCLUDEPY)
LDFLAGS = `pkg-config --libs sqlite3` $(BLDLIBRARY)

.PHONY: all
all: $(TARGET)

$(TARGET): $(OBJS)
	$(BLDSHARED) $^ $(LDFLAGS) -o $@

.PHONY: clean
clean:
	-rm -rf $(OBJS) $(TARGET) $(EXECUTABLE)

