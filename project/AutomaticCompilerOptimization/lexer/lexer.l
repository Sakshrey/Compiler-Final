%{
#include "parser.tab.h"
#include <string.h>
%}

%%
"int"       { return INT; }
"return"    { return RETURN; }
[0-9]+      { yylval.text = _strdup(yytext); return NUMBER; }
[a-zA-Z_][a-zA-Z0-9_]*  { yylval.text = _strdup(yytext); return ID; }

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

int yywrap()
{
    return 1;
}