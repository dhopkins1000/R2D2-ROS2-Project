#pragma once
#include <stdint.h>
#include <stdbool.h>

bool hmc5883l_init();
bool hmc5883l_read(float* x_T, float* y_T, float* z_T);
