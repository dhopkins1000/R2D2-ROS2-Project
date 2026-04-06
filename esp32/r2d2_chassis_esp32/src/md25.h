#pragma once
#include <stdint.h>

void    md25_init();
void    md25_set_speeds(uint8_t speed1, uint8_t speed2);
void    md25_stop();
void    md25_cmd_vel(double linear_x, double angular_z);
uint8_t md25_get_version();                                   // returns 0 on timeout
bool    md25_get_encoders(int32_t* enc1, int32_t* enc2);      // returns false on timeout
