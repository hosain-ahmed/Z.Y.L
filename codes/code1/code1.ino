#include <Wire.h>
#include <U8g2lib.h>

#include "SMARTDEVICE.h"
#include "BULB.h"
#include "FAN.h"
#include "OLEDDISPLAY.h"
#include "LIGHTMODE.h"
#include "AUTOCONTROLLER.h"


// Initialize OLED globally so OledDisplay.h can access it
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
LightMode currentLightMode = LightMode::MANUAL; 
// Create device instances
Bulb bulb1(13, "Bulb 1"); // true = low-level trigger relay
Bulb bulb2(14, "Bulb 2");
Fan deskFan(27, 0, "Desk Fan"); // Pin 27, PWM Channel 0
OledDisplay miniTV("Mini TV");
AutoController autoLed(4, "Auto LED"); 
// Load devices into the abstraction array
SmartDevice* devices[] = { &bulb1, &bulb2, &deskFan, &miniTV, &autoLed};
const int NUM_DEVICES = 5;

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setBusClock(400000); 
  
  // Startup screen
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(15, 35, "SYSTEM READY");
  u8g2.sendBuffer();
}

void loop() {
  // 1. Listen and route commands
  if (Serial.available()) {
    char cmd = Serial.read();
    for (int i = 0; i < NUM_DEVICES; i++) {
      devices[i]->handleCommand(cmd);
    }
  }

  // 2. Update background tasks (like drawing video frames)
  for (int i = 0; i < NUM_DEVICES; i++) {
    devices[i]->update();
  }
}