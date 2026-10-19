#include <stdio.h>
#include <string.h>
#include "algebraic_simplification.h"

void algebraicSimplification()
{
    for(int i = 0; i < irCount; i++)
    {
        if(strcmp(ir[i].op, "+") == 0)
        {
            if(strcmp(ir[i].arg2, "0") == 0)
            {
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
            else if(strcmp(ir[i].arg1, "0") == 0)
            {
                strcpy(ir[i].arg1, ir[i].arg2);
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
        }

        else if(strcmp(ir[i].op, "-") == 0)
        {
            if(strcmp(ir[i].arg2, "0") == 0)
            {
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
        }

        else if(strcmp(ir[i].op, "*") == 0)
        {
            if(strcmp(ir[i].arg2, "1") == 0)
            {
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
            else if(strcmp(ir[i].arg1, "1") == 0)
            {
                strcpy(ir[i].arg1, ir[i].arg2);
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
            else if(strcmp(ir[i].arg1, "0") == 0 ||
                    strcmp(ir[i].arg2, "0") == 0)
            {
                strcpy(ir[i].arg1, "0");
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
        }

        else if(strcmp(ir[i].op, "/") == 0)
        {
            if(strcmp(ir[i].arg2, "1") == 0)
            {
                strcpy(ir[i].op, "=");
                strcpy(ir[i].arg2, "");
            }
        }
    }
}