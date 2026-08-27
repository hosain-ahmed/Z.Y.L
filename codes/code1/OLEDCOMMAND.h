#ifndef OLEDCOMMAND_H
#define OLEDCOMMAND_H
#include <Arduino.h>

struct OledCommand {
  uint8_t cmdId;
  uint8_t payload;
};

#endif