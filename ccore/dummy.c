#include <stdio.h>
#include "currency.h"

int main()
{
    Currency *c1;
    Currency *c2;
    time_t t1;
    struct tm *t2;
    float rate = 12;

    currency_global_init("foo.db");
    c1 = currency_register("CAD", 2);
    c2 = currency_register("USD", 2);
    t1 = time(NULL);
    t2 = localtime(&t1);
    currency_set_CAD_value(t2, c2, 1.42);
    currency_getrate(t2, c1, c2, &rate);
    printf("%0.3f\n", rate);
    currency_global_deinit();
    return 0;
}
