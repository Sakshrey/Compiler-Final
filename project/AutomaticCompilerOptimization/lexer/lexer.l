%{
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "parser.tab.h"

/* Portable string-copy helper */
static char *copy_text(const char *s)
{
    size_t n = strlen(s) + 1;
    char *p = (char *)malloc(n);

    if (p != NULL)
    {
        memcpy(p, s, n);
    }

    return p;
}
%}

%%

"int"       { return INT; }
"return"    { return RETURN; }

[0-9]+      {
                yylval.text = copy_text(yytext);
                if (yylval.text == NULL)
                    return 0;
                return NUMBER;
            }

[a-zA-Z_][a-zA-Z0-9_]* {
                yylval.text = copy_text(yytext);
                if (yylval.text == NULL)
                    return 0;
                return ID;
            }

"="         { return ASSIGN; }
"+"         { return PLUS; }
"-"         { return MINUS; }
"*"         { return MULTIPLY; }
"/"         { return DIVIDE; }

"("         { return LPAREN; }
")"         { return RPAREN; }
";"         { return SEMICOLON; }

[ \t\n]+    { /* Ignore whitespace */ }

.           { return yytext[0]; }

%%

int yywrap(void)
{
    return 1;
}
