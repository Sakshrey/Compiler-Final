
#include <stdio.h>
#include <string.h>

#include "pass_manager.h"
#include "constant_folding.h"
#include "algebraic_simplification.h"
#include "dead_code_elimination.h"
#include "common_subexpression.h"

void runPass(char pass[])
{
    if (strcmp(pass, "CF") == 0)
    {
        constantFolding();
    }
    else if (strcmp(pass, "AS") == 0)
    {
        algebraicSimplification();
    }
    else if (strcmp(pass, "DCE") == 0)
    {
        deadCodeElimination();
    }
    else if (strcmp(pass, "CSE") == 0)
    {
        commonSubexpression();
    }
    else
    {
        fprintf(stderr, "Unknown optimization pass: %s\n", pass);
    }
}

void runPassSequence(const char *passes[], int count)
{
    for (int i = 0; i < count; i++)
    {
        char pass[10];

        snprintf(pass, sizeof(pass), "%s", passes[i]);

        printf("\nRunning optimization pass: %s\n", pass);
        runPass(pass);
    }
}
