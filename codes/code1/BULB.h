#ifndef BULB_H
#define BULB_H

#include <Arduino.h>
#include "SMARTDEVICE.h"
#include "LIGHTMODE.h"  // add this include

class Bulb : public SmartDevice {
  private:
    int pin;
    bool state;
    const char* name;

  public:
    // Notice we removed the "isLowLevelTrigger" stuff
    Bulb(int pinNumber, const char* deviceName) {
      pin = pinNumber;
      name = deviceName;
      state = false;
      
      pinMode(pin, OUTPUT);
      digitalWrite(pin, LOW); // Start OFF
    }

    

void handleCommand(char cmd) override {
  if (currentLightMode != LightMode::MANUAL) return;  // locked out during AUTO

  if (cmd == 'A' && strcmp(name, "Bulb 1") == 0) {
    toggle();
  } else if (cmd == 'B' && strcmp(name, "Bulb 2") == 0) {
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