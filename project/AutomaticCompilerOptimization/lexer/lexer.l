
%{
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "parser.tab.h"
%}

%%
"int"       { return INT; }
"return"    { return RETURN; }

[0-9]+      { yylval.text = strdup(yytext); return NUMBER; }
[a-zA-Z_][a-zA-Z0-9_]*  { yylval.text = strdup(yytext); return ID; }

"="         { return ASSIGN; }
"+"         { return PLUS; }
"-"         { return MINUS; }
"*"         { return MULTIPLY; }
"/"         { return DIVIDE; }

"("         { return LPAREN; }
")"         { return RPAREN; }
";"         { return SEMICOLON; }

[ \t\n]+    { }
.           { return yytext[0]; }
%%

int yywrap(void)
{
    return 1;
}
