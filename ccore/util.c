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
/* Time */

static time_t g_patched_today = 0;

time_t
today()
{
    if (g_patched_today > 0) {
        return g_patched_today;
    }
    time_t r = time(NULL);
    r /= 60 * 60 * 24;
    r *= 60 * 60 * 24;
    return r;
}

void
today_patch(time_t today)
{
    g_patched_today = today;
}

static time_t g_prevnow = 0;

time_t
now()
{
    time_t r = time(NULL);
    if (r <= g_prevnow) {
        r = g_prevnow + 1;
    }
    g_prevnow = r;
    return r;
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
