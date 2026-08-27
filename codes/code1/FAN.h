#ifndef FAN_H
#define FAN_H

#include <Arduino.h>
#include "SMARTDEVICE.h"

class Fan : public SmartDevice {
  private:
    int pin;
    int pwmChannel;
    const char* name;

  public:
    Fan(int pinNumber, int channel, const char* deviceName) {
      pin = pinNumber;
      pwmChannel = channel;
      name = deviceName;

      // ESP32 PWM Setup: Channel, Freq (5kHz), Resolution (8-bit)
      ledcSetup(pwmChannel, 5000, 8);
      ledcAttachPin(pin, pwmChannel);
      ledcWrite(pwmChannel, 0); 
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      if (cmdId == 0x0B) { // CMD_FAN_SPEED
        // Directly write the 0-255 speed value sent from Python
        ledcWrite(pwmChannel, payload);
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