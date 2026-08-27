#ifndef FAN_H
#define FAN_H

#include <Arduino.h>
#include "SMARTDEVICE.h"

class Fan : public SmartDevice {
  private:
    int pin;
    int pwmChannel;
    bool state;
    const char* name;
    const int maxSpeed = 255; // Caps effective voltage from 16.8V down to ~12V

  public:
    Fan(int pinNumber, int channel, const char* deviceName) {
      pin = pinNumber;
      pwmChannel = channel;
      name = deviceName;
      state = false;

      // ESP32 PWM Setup: Channel, Freq (5kHz), Resolution (8-bit)
      ledcSetup(pwmChannel, 5000, 8);
      ledcAttachPin(pin, pwmChannel);
      ledcWrite(pwmChannel, 0); 
    }

    void handleCommand(char cmd) override {
      if (cmd == 'F') { // Let's say 'F' is your gesture command for Fan
        state = !state;
        ledcWrite(pwmChannel, state ? maxSpeed : 0);
      }
    }

    void update() override {
      // Fan runs continuously via hardware PWM, no manual loop updates needed
    }

    const char* getName() override {
      return name;
    }
};

#endif