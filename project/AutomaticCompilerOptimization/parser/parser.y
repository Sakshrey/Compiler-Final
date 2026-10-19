
%code requires
{
    typedef struct ASTNode ASTNode;
}

%{
#include <stdio.h>
#include <stdlib.h>

#include "ast/ast.h"
#include "ir/ir.h"
#include "optimizer/pass_manager.h"

int yylex(void);
void yyerror(const char *s);

ASTNode *root;
%}

%union
{
    ASTNode *node;
    char *text;
}

%token INT RETURN
%token <text> ID NUMBER
%token ASSIGN PLUS MINUS MULTIPLY DIVIDE
%token LPAREN RPAREN SEMICOLON

%type <node> program statements statement declaration assignment
%type <node> return_statement expression term factor

%%

program:
    statements
    {
        root = $1;
        $$ = $1;
    }
    ;

statements:
    statements statement
    {
        $$ = createNode("Statements", "", $1, $2);
    }
    | statement
    {
        $$ = $1;
    }
    ;

statement:
    declaration
    {
        $$ = $1;
    }
    | assignment
    {
        $$ = $1;
    }
    | return_statement
    {
        $$ = $1;
    }
    ;

declaration:
    INT ID SEMICOLON
    {
        $$ = createNode("Declaration", $2, NULL, NULL);
    }
    | INT ID ASSIGN expression SEMICOLON
    {
        ASTNode *id = createNode("Identifier", $2, NULL, NULL);
        $$ = createNode("Declaration", "", id, $4);
    }
    ;

assignment:
    ID ASSIGN expression SEMICOLON
    {
        ASTNode *id = createNode("Identifier", $1, NULL, NULL);
        $$ = createNode("Assignment", "", id, $3);
    }
    ;

return_statement:
    RETURN expression SEMICOLON
    {
        $$ = createNode("Return", "", $2, NULL);
    }
    ;

expression:
    expression PLUS term
    {
        $$ = createNode("Operator", "+", $1, $3);
    }
    | expression MINUS term
    {
        $$ = createNode("Operator", "-", $1, $3);
    }
    | term
    {
        $$ = $1;
    }
    ;

term:
    term MULTIPLY factor
    {
        $$ = createNode("Operator", "*", $1, $3);
    }
    | term DIVIDE factor
    {
        $$ = createNode("Operator", "/", $1, $3);
    }
    | factor
    {
        $$ = $1;
    }
    ;

factor:
    NUMBER
    {
        $$ = createNode("Number", $1, NULL, NULL);
    }
    | ID
    {
        $$ = createNode("Identifier", $1, NULL, NULL);
    }
    | LPAREN expression RPAREN
    {
        $$ = $2;
    }
    ;

%%

void yyerror(const char *s)
{
    fprintf(stderr, "Invalid syntax: %s\n", s);
}

int main(int argc, char *argv[])
{
    const char *defaultPasses[] = {"CF", "AS", "DCE", "CSE"};
    const char *passes[100];
    int passCount = 0;

    if (argc > 101)
    {
        fprintf(stderr, "Error: Maximum 100 optimization passes allowed.\n");
        return 1;
    }

    if (argc == 1)
    {
        for (int i = 0; i < 4; i++)
        {
            passes[passCount++] = defaultPasses[i];
        }
    }
    else
    {
        for (int i = 1; i < argc; i++)
        {
            passes[passCount++] = argv[i];
        }
    }

    printf("Enter program:\n");

    if (yyparse() != 0)
    {
        fprintf(stderr, "Parsing failed.\n");
        return 1;
    }

    printf("\nAST:\n");
    printAST(root, 0);

    generateIR(root);

    printf("\nBefore Optimization:\n");
    printIR();

    printf("\nExecuting Optimization Passes:\n");
    runPassSequence(passes, passCount);

    printf("\nAfter Optimization:\n");
    printIR();

    return 0;
}
