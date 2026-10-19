
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>

#include "constant_folding.h"

#define MAX_CONSTANTS 1000
#define VALUE_SIZE 64

typedef struct {
    char name[VALUE_SIZE];
    int value;
    int valid;
} Constant;

static Constant constants[MAX_CONSTANTS];
static int constantCount = 0;

int isNumber(char str[])
{
    if (str[0] == '\0')
        return 0;

    int i = 0;

    if (str[0] == '-' || str[0] == '+')
        i++;

    if (str[i] == '\0')
        return 0;

    for (; str[i] != '\0'; i++) {
        if (str[i] < '0' || str[i] > '9')
            return 0;
    }

    return 1;
}

static int findConstant(const char *name)
{
    for (int i = 0; i < constantCount; i++) {
        if (constants[i].valid &&
            strcmp(constants[i].name, name) == 0)
            return i;
    }

    return -1;
}

static void invalidateConstant(const char *name)
{
    int index = findConstant(name);

    if (index >= 0)
        constants[index].valid = 0;
}

static void setConstant(const char *name, int value)
{
    int index = findConstant(name);

    if (index < 0) {
        if (constantCount >= MAX_CONSTANTS)
            return;

        index = constantCount++;

        snprintf(constants[index].name,
                 sizeof(constants[index].name),
                 "%s", name);
    }

    constants[index].value = value;
    constants[index].valid = 1;
}

static int getConstant(const char *name, int *value)
{
    if (isNumber((char *)name)) {
        char *end = NULL;
        long parsed = strtol(name, &end, 10);

        if (*end != '\0' || parsed < INT_MIN ||
            parsed > INT_MAX)
            return 0;

        *value = (int)parsed;
        return 1;
    }

    int index = findConstant(name);

    if (index < 0)
        return 0;

    *value = constants[index].value;
    return 1;
}

void constantFolding(void)
{
    constantCount = 0;

    for (int i = 0; i < irCount; i++) {

        /* Handle assignments: destination = source. */
        if (strcmp(ir[i].op, "=") == 0) {
            int value;

            if (getConstant(ir[i].arg1, &value)) {
                setConstant(ir[i].result, value);

                snprintf(ir[i].arg1,
                         sizeof(ir[i].arg1),
                         "%d", value);
            } else {
                invalidateConstant(ir[i].result);
            }

            continue;
        }

        /* Do not treat return instructions as assignments. */
        if (strcmp(ir[i].result, "return") == 0)
            continue;

        /* Process arithmetic instructions only. */
        if (strcmp(ir[i].op, "+") != 0 &&
            strcmp(ir[i].op, "-") != 0 &&
            strcmp(ir[i].op, "*") != 0 &&
            strcmp(ir[i].op, "/") != 0) {
            continue;
        }

        int a, b;

        if (getConstant(ir[i].arg1, &a)) {
            snprintf(ir[i].arg1,
                     sizeof(ir[i].arg1),
                     "%d", a);
        }

        if (getConstant(ir[i].arg2, &b)) {
            snprintf(ir[i].arg2,
                     sizeof(ir[i].arg2),
                     "%d", b);
        }

        if (!getConstant(ir[i].arg1, &a) ||
            !getConstant(ir[i].arg2, &b)) {
            invalidateConstant(ir[i].result);
            continue;
        }

        long long result;

        if (strcmp(ir[i].op, "+") == 0) {
            result = (long long)a + b;
        } else if (strcmp(ir[i].op, "-") == 0) {
            result = (long long)a - b;
        } else if (strcmp(ir[i].op, "*") == 0) {
            result = (long long)a * b;
        } else {
            if (b == 0 ||
                (a == INT_MIN && b == -1)) {
                invalidateConstant(ir[i].result);
                continue;
            }

            result = a / b;
        }

        if (result < INT_MIN || result > INT_MAX) {
            invalidateConstant(ir[i].result);
            continue;
        }

        /* Convert the arithmetic instruction into a constant. */
        snprintf(ir[i].arg1,
                 sizeof(ir[i].arg1),
                 "%lld", result);

        ir[i].op[0] = '\0';
        ir[i].arg2[0] = '\0';

        setConstant(ir[i].result, (int)result);
    }
}
