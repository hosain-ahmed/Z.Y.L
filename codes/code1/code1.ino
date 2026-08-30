#include <Wire.h>
#include <U8g2lib.h>
#include <LittleFS.h>  // <-- ADDED: Include the LittleFS library

#include "SMARTDEVICE.h"
#include "BULB.h"
#include "FAN.h"
#include "OLEDDISPLAY.h"
#include "LIGHTMODE.h"
#include "AUTOCONTROLLER.h"
#include "PROTOCOLPARSER.h"
#include "OLEDCOMMAND.h"

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);
LightMode currentLightMode = LightMode::MANUAL;

Bulb bulb1(13, "Bulb 1");
Bulb bulb2(14, "Bulb 2");
Fan deskFan(27, 0, "Desk Fan");
AutoController autoLed(4, "Auto LED");

// NOTE: OledDisplay is no longer in this global array — it lives entirely
// on Core 1 now, created inside oledTask().
SmartDevice* devices[] = { &bulb1, &bulb2, &deskFan, &autoLed };
const int NUM_DEVICES = 4;

ProtocolParser parser;
QueueHandle_t oledQueue;

// Returns true if this command belongs to the OLED/TV subsystem
bool isOledCommand(uint8_t cmdId) {
  return cmdId >= 0x05 && cmdId <= 0x0A;  // TV_ON..TV_PREV range from your protocol
}

// ---------- Core 0 task: serial read + protocol parse + dispatch ----------
void core0Task(void *param) {
  for (;;) {
    while (Serial.available()) {
      Command cmd;
      if (parser.feed(Serial.read(), cmd)) {
        if (isOledCommand(cmd.cmdId)) {
          OledCommand oc = { cmd.cmdId, cmd.payload };
          xQueueSend(oledQueue, &oc, 0);  // non-blocking send
        } else {
          for (int i = 0; i < NUM_DEVICES; i++) {
            devices[i]->handleCommand(cmd.cmdId, cmd.payload);
          }
        }
      }
    }
    for (int i = 0; i < NUM_DEVICES; i++) devices[i]->update();
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

// ---------- Core 1 task: owns OledDisplay entirely ----------
void oledTask(void *param) {
  OledDisplay miniTV("Mini TV", 34, 32);

  for (;;) {
    OledCommand oc;
    while (xQueueReceive(oledQueue, &oc, 0) == pdTRUE) {
      miniTV.handleCommand(oc.cmdId, oc.payload);
    }
    miniTV.update();
    vTaskDelay(pdMS_TO_TICKS(2));  // paces frame rate, prevents starving other tasks
  }
}

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setBusClock(400000);

  // <-- ADDED: Mount LittleFS before starting your FreeRTOS tasks
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS mount failed!");
  }

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(15, 35, "SYSTEM READY");
  u8g2.sendBuffer();

  oledQueue = xQueueCreate(10, sizeof(OledCommand));

  xTaskCreatePinnedToCore(core0Task, "Core0Main", 4096, NULL, 1, NULL, 0);
  xTaskCreatePinnedToCore(oledTask,  "OledCore1", 4096, NULL, 1, NULL, 1);
}

void loop() {
  vTaskDelete(NULL);  // main loop unused — everything runs in the two pinned tasks
}