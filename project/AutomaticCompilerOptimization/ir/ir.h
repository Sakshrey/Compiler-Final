#ifndef IR_H
#define IR_H

#include "../ast/ast.h"

typedef struct IRNode
{
    char result[20];
    char arg1[20];
    char op[10];
    char arg2[20];
} IRNode;

extern IRNode ir[100];
extern int irCount;

void generateIR(ASTNode *node);
void printIR();

#endif