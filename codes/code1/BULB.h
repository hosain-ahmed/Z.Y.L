#ifndef BULB_H
#define BULB_H

#include <Arduino.h>
#include "SMARTDEVICE.h"
#include "LIGHTMODE.h"  

class Bulb : public SmartDevice {
  private:
    int pin;
    bool state;
    const char* name;

  public:
    Bulb(int pinNumber, const char* deviceName) {
      pin = pinNumber;
      name = deviceName;
      state = false;
      
      pinMode(pin, OUTPUT);
      digitalWrite(pin, LOW); // Start OFF
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      if (currentLightMode != LightMode::MANUAL) return;  // locked out during AUTO

      if (cmdId == 0x01 && strcmp(name, "Bulb 1") == 0) {
        toggle();
      } else if (cmdId == 0x02 && strcmp(name, "Bulb 2") == 0) {
        toggle();
      }
    }

    void update() override {
      // Basic LEDs don't need continuous background updates
    }

    const char* getName() override {
      return name;
    }

  private:
    void toggle() {
      state = !state;
      digitalWrite(pin, state ? HIGH : LOW); // HIGH turns the transistor ON
    }
};

#endif