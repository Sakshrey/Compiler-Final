#ifndef AST_H
#define AST_H

typedef struct ASTNode
{
    char type[20];
    char value[20];
    struct ASTNode *left;
    struct ASTNode *right;
} ASTNode;

ASTNode* createNode(char type[], char value[], ASTNode *left, ASTNode *right);
void printAST(ASTNode *node, int level);

#endif