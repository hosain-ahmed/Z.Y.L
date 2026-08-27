#ifndef AUTOCONTROLLER_H
#define AUTOCONTROLLER_H

#include <Arduino.h>
#include "SMARTDEVICE.h"
#include "LIGHTMODE.h"

class AutoController : public SmartDevice {
  private:
    int pin;
    const char* name;

  public:
    AutoController(int pinNumber, const char* deviceName) {
      pin = pinNumber;
      name = deviceName;
      pinMode(pin, OUTPUT);
      digitalWrite(pin, LOW);
    }

    void handleCommand(char cmd) override {
      if (cmd == 'H') {
        currentLightMode = LightMode::AUTO;
        digitalWrite(pin, HIGH);
      } else if (cmd == 'I') {
        currentLightMode = LightMode::MANUAL;
        digitalWrite(pin, LOW);
      }
    }

    void update() override {}
    const char* getName() override { return name; }
};

#endif