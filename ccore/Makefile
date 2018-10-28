TARGET = ccore.a
EXECUTABLE = ccore

SRCS = currency.c
OBJS = $(SRCS:%.c=%.o)

LDFLAGS = `pkg-config --libs sqlite3`

.PHONY: all
all: $(TARGET) $(EXECUTABLE)

$(EXECUTABLE): $(TARGET) dummy.c
	$(CC) $(LDFLAGS) -o $@ dummy.c $(TARGET)

$(TARGET): $(OBJS)
	ar rcs $@ $^

.PHONY: clean
clean:
	-rm -rf $(OBJS) $(TARGET) $(EXECUTABLE)

