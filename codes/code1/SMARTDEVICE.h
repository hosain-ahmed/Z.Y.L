#ifndef SMARTDEVICE_H
#define SMARTDEVICE_H

#include <Arduino.h>

class SmartDevice {
    public: 
        virtual void handleCommand(uint8_t cmdId, uint8_t payload) = 0;
        virtual void update() = 0;
        virtual const char* getName() = 0;
};

#endif