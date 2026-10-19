#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "ast.h"

ASTNode* createNode(char type[], char value[], ASTNode *left, ASTNode *right)
{
    ASTNode *node = malloc(sizeof(ASTNode));

    strcpy(node->type, type);
    strcpy(node->value, value);

    node->left = left;
    node->right = right;

    return node;
}

void printAST(ASTNode *node, int level)
{
    if(node == NULL)
        return;

    for(int i = 0; i < level; i++)
        printf("  ");

    printf("%s", node->type);

    if(strlen(node->value) > 0)
        printf(": %s", node->value);

    printf("\n");

    printAST(node->left, level + 1);
    printAST(node->right, level + 1);
}