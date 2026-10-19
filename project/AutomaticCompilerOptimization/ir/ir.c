#include <stdio.h>
#include <string.h>
#include "ir.h"

IRNode ir[100];
int irCount = 0;
int tempCount = 1;

char* generateExpression(ASTNode *node)
{
    static char result[20];

    if(node == NULL)
        return "";

    if(strcmp(node->type, "Number") == 0)
    {
        strcpy(result, node->value);
        return result;
    }

    if(strcmp(node->type, "Identifier") == 0)
    {
        strcpy(result, node->value);
        return result;
    }

    if(strcmp(node->type, "Operator") == 0)
    {
        char left[20];
        char right[20];
        char temp[20];

        strcpy(left, generateExpression(node->left));
        strcpy(right, generateExpression(node->right));

        sprintf(temp, "t%d", tempCount++);

        strcpy(ir[irCount].result, temp);
        strcpy(ir[irCount].arg1, left);
        strcpy(ir[irCount].op, node->value);
        strcpy(ir[irCount].arg2, right);

        irCount++;

        strcpy(result, temp);
        return result;
    }

    return "";
}

void generateIR(ASTNode *node)
{
    if(node == NULL)
        return;

    if(strcmp(node->type, "Statements") == 0)
    {
        generateIR(node->left);
        generateIR(node->right);
    }
    else if(strcmp(node->type, "Declaration") == 0)
    {
        if(node->right != NULL)
        {
            char value[20];

            strcpy(value, generateExpression(node->right));

            strcpy(ir[irCount].result, node->left->value);
            strcpy(ir[irCount].arg1, value);
            strcpy(ir[irCount].op, "=");
            strcpy(ir[irCount].arg2, "");

            irCount++;
        }
    }
    else if(strcmp(node->type, "Assignment") == 0)
    {
        char value[20];

        strcpy(value, generateExpression(node->right));

        strcpy(ir[irCount].result, node->left->value);
        strcpy(ir[irCount].arg1, value);
        strcpy(ir[irCount].op, "=");
        strcpy(ir[irCount].arg2, "");

        irCount++;
    }
    else if(strcmp(node->type, "Return") == 0)
    {
        char value[20];

        strcpy(value, generateExpression(node->left));

        strcpy(ir[irCount].result, "return");
        strcpy(ir[irCount].arg1, value);
        strcpy(ir[irCount].op, "");
        strcpy(ir[irCount].arg2, "");

        irCount++;
    }
}

void printIR()
{
    printf("\nThree Address Code:\n");

    for(int i = 0; i < irCount; i++)
    {
        if(strcmp(ir[i].result, "return") == 0)
        {
            printf("return %s\n", ir[i].arg1);
        }
        else if(strcmp(ir[i].op, "=") == 0)
        {
            printf("%s = %s\n", ir[i].result, ir[i].arg1);
        }
        else
        {
            printf("%s = %s %s %s\n",
                   ir[i].result,
                   ir[i].arg1,
                   ir[i].op,
                   ir[i].arg2);
        }
    }
}