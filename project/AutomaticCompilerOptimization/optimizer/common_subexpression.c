#include <stdio.h>
#include <string.h>
#include "common_subexpression.h"

int variableChanged(int start, int end, char variable[])
{
    for(int i = start; i < end; i++)
    {
        if(strcmp(ir[i].result, variable) == 0)
            return 1;
    }

    return 0;
}

void commonSubexpression()
{
    for(int i = 0; i < irCount; i++)
    {
        if(strcmp(ir[i].op, "+") != 0 &&
           strcmp(ir[i].op, "-") != 0 &&
           strcmp(ir[i].op, "*") != 0 &&
           strcmp(ir[i].op, "/") != 0)
        {
            continue;
        }

        for(int j = 0; j < i; j++)
        {
            if(strcmp(ir[j].op, ir[i].op) == 0 &&
               strcmp(ir[j].arg1, ir[i].arg1) == 0 &&
               strcmp(ir[j].arg2, ir[i].arg2) == 0)
            {
                if(variableChanged(j + 1, i, ir[i].arg1))
                    continue;

                if(variableChanged(j + 1, i, ir[i].arg2))
                    continue;

                strcpy(ir[i].arg1, ir[j].result);
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");

                break;
            }
        }
    }
}