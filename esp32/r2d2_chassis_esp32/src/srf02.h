#pragma once
#include <stdint.h>
#include <stdbool.h>

void    srf02_trigger();
bool    srf02_read_cm(uint16_t* dist_cm);
