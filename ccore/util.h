#include <stdbool.h>

/* String management in ccore
 *
 * As a general rules, all structures in ccore own the strings they hold, and
 * those are malloc'ed. One exception to this is the empty string (maybe I'll
 * regret the exception down the road...): it's too common to dynamically alloc
 * each time, so when the value to set is an emptry string, we don't malloc. We
 * directly assign a statically declared "" value to it. This means that when
 * deinit'ing structures, we need to skip empty strings.
 *
 * `NULL` values are permitted and handled, they represent an absence of value
 * (replace Python's `None`).
 *
 * It's this logic that is implemented in those str*() functions below.
 */

/* Malloc and set `dst` to a copy of `src`.
 *
 * This manages lifecycle of `dst`: it mallocs and frees `dst`, except when
 * `dst` is "", then it doesn't free it. Symmetrically, when `src` is empty,
 * we set `dst` to "", a static value, not mallocated.
 *
 * If `dst` points to NULL, we consider us to be in a "initial set" situation,
 * so we free nothing.
 *
 * Returns false on error.
 */
bool
strset(char **dst, const char *src);
/* Frees a string created through strset()
 *
 * Returns false on error
 */
bool
strfree(char **dst);

bool
strclone(char **dst, const char *src);

/* Other */

/* Returns whether pointer `target` is is NULL-terminated list `list`
 */
bool
pointer_in_list(void **list, void *target);
