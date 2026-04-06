#pragma once
#include <stdint.h>

void md25_init();
void md25_set_speeds(uint8_t speed1, uint8_t speed2);
void md25_stop();
void md25_cmd_vel(double linear_x, double angular_z);
