
#ifndef PASS_MANAGER_H
#define PASS_MANAGER_H

#include "../ir/ir.h"

void runPass(char pass[]);
void runPassSequence(const char *passes[], int count);

#endif
