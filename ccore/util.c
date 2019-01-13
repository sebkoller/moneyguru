#include <stdlib.h>
#include <string.h>
#include <ctype.h>
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

bool
strstrip(char **dst, const char *src)
{
    int len = strlen(src);
    int begin = 0;
    int end = len - 1;
    if (!len) {
        return false;
    }
    while (isspace(src[begin])) {
        begin++;
    }
    if (begin == len) {
        // all spaces
        *dst = malloc(1);
        *dst[0] = '\0';
        return true;
    }
    while (end > begin && isspace(src[end])) {
        end--;
    }
    if (begin == 0 && end == (len - 1)) {
        // nothing to trim
        return false;
    }
    len = end - begin + 1;
    *dst = malloc(len + 1);
    memcpy(*dst, &src[begin], len);
    (*dst)[len] = '\0';
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

int
listlen(void **list)
{
    if (list == NULL) {
        return 0;
    }
    int res = 0;
    while (*list != NULL) {
        res++;
        list++;
    }
    return res;
}
