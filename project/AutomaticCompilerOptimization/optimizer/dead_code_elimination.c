
#include <stdio.h>
#include <string.h>
#include "dead_code_elimination.h"

static int isUsedLater(int index, const char *variable)
{
    for (int i = index + 1; i < irCount; i++) {
        /* A later instruction overwrites the variable. */
        if (strcmp(ir[i].result, variable) == 0 &&
            strcmp(ir[i].result, "return") != 0) {
            return 0;
        }

        if (strcmp(ir[i].arg1, variable) == 0 ||
            strcmp(ir[i].arg2, variable) == 0) {
            return 1;
        }
    }

    return 0;
}

void deadCodeElimination(void)
{
    int changed;

    do {
        changed = 0;

        for (int i = 0; i < irCount; i++) {
            /* Never remove a return instruction. */
            if (strcmp(ir[i].result, "return") == 0)
                continue;

            /* Only remove instructions that produce a result. */
            if (ir[i].result[0] == '\0')
                continue;

            /*
             * Remove an unused assignment or temporary calculation.
             * Keep division because it may have observable behavior
             * in a more complete compiler.
             */
            if (strcmp(ir[i].op, "/") == 0)
                continue;

            if (!isUsedLater(i, ir[i].result)) {
                for (int j = i; j < irCount - 1; j++) {
                    ir[j] = ir[j + 1];
                }

                irCount--;
                changed = 1;
                break;
            }
        }
    } while (changed);
}
