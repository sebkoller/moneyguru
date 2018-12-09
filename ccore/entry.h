#pragma once

#include "amount.h"
#include "split.h"

/* An Entry represents a split in the context of an account */
typedef struct {
    Split *split;
    /* Running balance in the account after the split occurs. */
    Amount balance;
} Entry;

