#include <stdlib.h>
#include <string.h>
#include "util.h"

bool
strset(char **dst, const char *src)
{
    if (!strfree(dst)) {
        return false;
    }
    if (src == NULL) {
        *dst = NULL;
        return true;
    }
    if (src[0] != '\0') {
        int len = strlen(src);
        *dst = malloc(len+1);
        strncpy(*dst, src, len+1);
    } else {
        *dst = "";
    }
    return true;
}

bool
strfree(char **dst)
{
    if (dst == NULL) {
        // not supposed to happen
        return false;
    }
    if (*dst == NULL || *dst[0] == '\0') {
        // nothing to free
        return true;
    }
    free(*dst);
    *dst = NULL;
    return true;
}

bool
strclone(char **dst, const char *src)
{
    if (!strfree(dst)) {
        return false;
    }
    if (src == NULL) {
        *dst = NULL;
        return true;
    }
    int len = strlen(src);
    if (len) {
        *dst = malloc(len+1);
        strncpy(*dst, src, len+1);
    } else {
        *dst = "";
    }
    return true;
}

/* Other */
bool
pointer_in_list(void **list, void *target)
{
    while (*list != NULL) {
        if (*list == target) {
            return true;
        }
        list++;
    }
    return false;
}
