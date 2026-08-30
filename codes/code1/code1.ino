#include <Wire.h>
#include <U8g2lib.h>
#include <LittleFS.h>

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

SmartDevice* devices[] = { &bulb1, &bulb2, &deskFan, &autoLed };
const int NUM_DEVICES = 4;

ProtocolParser parser;
QueueHandle_t oledQueue;

// === Global variables for Core 1 suspension and display access ===
OledDisplay* pMiniTV = nullptr;
TaskHandle_t TaskCore1Handle = NULL;

// Returns true if this command belongs to the OLED/TV subsystem
bool isOledCommand(uint8_t cmdId) {
  return cmdId >= 0x05 && cmdId <= 0x0A;
}

// === Download routine runs entirely on Core 0 ===
void downloadRoutine(const String &filename) {
  Serial.print("FETCH:");
  Serial.println(filename);

  // Wait specifically for the 0x10 "starting now" packet, ignoring anything else
  Command cmd;
  bool gotStart = false;
  unsigned long waitStart = millis();
  
  while (!gotStart && millis() - waitStart < 10000) {  // 10s timeout
    if (Serial.available()) {
      if (parser.feed(Serial.read(), cmd) && cmd.cmdId == 0x10) {
        gotStart = true;
      }
    }
    // <-- FIXED: Give the system a tiny break to feed the watchdog
    vTaskDelay(1); 
  }
  
  if (!gotStart) {
    pMiniTV->onDownloadFailed();
    return;
  }

  vTaskSuspend(TaskCore1Handle);  // no concurrent access to OledDisplay/LittleFS during write

  String incomingName = Serial.readStringUntil('\n');
  incomingName.trim();

  uint8_t sizeBytes[4];
  Serial.readBytes(sizeBytes, 4);
  uint32_t fileSize = sizeBytes[0] | (sizeBytes[1] << 8) | (sizeBytes[2] << 16) | (sizeBytes[3] << 24);

  File f = LittleFS.open("/" + incomingName, "w");
  if (!f) {
    Serial.println("OPEN_WRITE_FAIL");
    vTaskResume(TaskCore1Handle);
    pMiniTV->onDownloadFailed();
    return;
  }

  uint32_t received = 0;
  uint8_t buf[128];
  bool ok = true;
  
  while (received < fileSize) {
    size_t toRead = min((uint32_t)128, fileSize - received);
    size_t got = Serial.readBytes(buf, toRead);
    if (got > 0) {
      f.write(buf, got);
      received += got;
      Serial.println("ACK");
    } else {
      Serial.println("TIMEOUT_NO_DATA");
      ok = false;
      break;
    }
    // <-- FIXED: Give the system a tiny break after every chunk
    vTaskDelay(1); 
  }
  
  f.close();

  vTaskResume(TaskCore1Handle);

  if (ok && received == fileSize) {
    Serial.println("TRANSFER_COMPLETE");
    pMiniTV->onDownloadComplete(incomingName);
  } else {
    pMiniTV->onDownloadFailed();
  }
}

// ---------- Core 0 task: serial read + protocol parse + dispatch ----------
void core0Task(void *param) {
  for (;;) {
    while (Serial.available()) {
      Command cmd;
      if (parser.feed(Serial.read(), cmd)) {
        if (cmd.cmdId == 0x11) {
          // Video list sync — read the name, then apply it with Core1 suspended
          String vName = Serial.readStringUntil('\n');
          vName.trim();
          vTaskSuspend(TaskCore1Handle);
          if (pMiniTV != nullptr) pMiniTV->addVideoToList(vName);
          vTaskResume(TaskCore1Handle);
        } else if (isOledCommand(cmd.cmdId)) {
          OledCommand oc = { cmd.cmdId, cmd.payload };
          xQueueSend(oledQueue, &oc, 0);  // non-blocking send
        } else {
          for (int i = 0; i < NUM_DEVICES; i++) {
            devices[i]->handleCommand(cmd.cmdId, cmd.payload);
          }
        }
      }
    }

    // Check if the menu (Core1) is asking us to fetch a file
    if (pMiniTV != nullptr && pMiniTV->isDownloadRequested()) {
      downloadRoutine(pMiniTV->getPendingFilename());
    }

    for (int i = 0; i < NUM_DEVICES; i++) devices[i]->update();
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}

// ---------- Core 1 task: owns OledDisplay entirely ----------
void oledTask(void *param) {
  pMiniTV = new OledDisplay("Mini TV", 34, 32);  // created once, here

  for (;;) {
    OledCommand oc;
    while (xQueueReceive(oledQueue, &oc, 0) == pdTRUE) {
      pMiniTV->handleCommand(oc.cmdId, oc.payload);
    }
    pMiniTV->update();
    vTaskDelay(pdMS_TO_TICKS(30));
  }
}

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setBusClock(400000);

  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS mount failed!");
  }
  // LittleFS.format(); // WIPES ALL FILES

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(15, 35, "SYSTEM READY");
  u8g2.sendBuffer();

  oledQueue = xQueueCreate(10, sizeof(OledCommand));

  xTaskCreatePinnedToCore(core0Task, "Core0Main", 4096, NULL, 1, NULL, 0);
  
  // === UPDATED: Passing &TaskCore1Handle instead of NULL ===
  xTaskCreatePinnedToCore(oledTask,  "OledCore1", 4096, NULL, 1, &TaskCore1Handle, 1);

  // Add the line right here, before the bracket!
  Serial.println("BOOT_READY");
}

void loop() {
  vTaskDelete(NULL);  // main loop unused — everything runs in the two pinned tasks
}