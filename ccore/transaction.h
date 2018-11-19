#include <time.h>

typedef struct {
    Account *account;
    Amount *amount;
} Split;

typedef struct {
    struct tm date;
    Split *splits;
}


