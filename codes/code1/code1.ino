#include <Wire.h>
#include <U8g2lib.h>
#include "SMARTDEVICE.h"
#include "BULB.h"
#include "FAN.h"
#include "OLEDDISPLAY.h"
#include "LIGHTMODE.h"
#include "AUTOCONTROLLER.h"
#include "PROTOCOLPARSER.h"
#include "OLEDCOMMAND.h"
#include <LittleFS.h>
#include <freertos/task.h>

// --- HARDWARE PINS ---
const int POT_PIN = 34; // Potentiometer for scrolling
const int BTN_PIN = 32; // Push button for selecting

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
TaskHandle_t TaskCore1 = NULL;      // Handle required to suspend Core 1 during downloads
OledDisplay* pMiniTV = nullptr;     // Global pointer to access the TV from Core 0
int globalLruSlot = 0;              // Mirrors the LRU slot inside the OLED class

bool isOledCommand(uint8_t cmdId) {
  return cmdId >= 0x05 && cmdId <= 0x0A;  
}

void downloadRoutine() {
  Serial.println("READY"); 

  String videoName = Serial.readStringUntil('\n');
  videoName.trim();

  uint32_t fileSize = 0;
  while (Serial.available() < 4) { vTaskDelay(pdMS_TO_TICKS(1)); }
  Serial.readBytes((char*)&fileSize, 4);

  if (TaskCore1 != NULL) vTaskSuspend(TaskCore1);

  String path = "/slot" + String(globalLruSlot) + ".bin";
  File file = LittleFS.open(path, "w");
  if (!file) {
    Serial.println("FAIL");
    if (TaskCore1 != NULL) vTaskResume(TaskCore1);
    return;
  }

  // --- NEW FIX: Buffer-safe byte-by-byte reading with 128-byte chunks ---
  uint32_t bytesReceived = 0;
  uint8_t buffer[128]; 

  while (bytesReceived < fileSize) {
    uint32_t chunkTarget = fileSize - bytesReceived;
    if (chunkTarget > 128) chunkTarget = 128; 

    uint32_t chunkReceived = 0;
    
    // Read bytes exactly as they arrive to prevent buffer overflow
    while (chunkReceived < chunkTarget) {
      if (Serial.available()) {
        buffer[chunkReceived] = Serial.read();
        chunkReceived++;
      } else {
        vTaskDelay(pdMS_TO_TICKS(1)); 
      }
    }
    
    file.write(buffer, chunkTarget);
    bytesReceived += chunkTarget;
    
    Serial.println("ACK"); 
  }
  
  file.close();
  globalLruSlot = (globalLruSlot == 0) ? 1 : 0;
  
  if (pMiniTV != nullptr) {
    pMiniTV->cacheDownloadComplete(videoName);
  }

  if (TaskCore1 != NULL) vTaskResume(TaskCore1);
  Serial.println("DONE");
}

// ---------- Core 0 task: serial read + protocol parse + dispatch ----------
void core0Task(void *param) {
  for (;;) {
    while (Serial.available()) {
      Command cmd;
      if (parser.feed(Serial.read(), cmd)) {
        
        // --- MEDIA SERVER INTERCEPTS ---
        if (cmd.cmdId == 0x10) {
          // Python is sending a file
          downloadRoutine(); 
          continue; 
        }
        else if (cmd.cmdId == 0x11) {
          // Python is syncing the PC library list
          String vName = Serial.readStringUntil('\n');
          vName.trim();
          if (pMiniTV != nullptr) pMiniTV->addVideoToList(vName);
          continue;
        }
        // -------------------------------

        if (isOledCommand(cmd.cmdId)) {
          OledCommand oc = { cmd.cmdId, cmd.payload };
          xQueueSend(oledQueue, &oc, 0); 
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
  // Instantiate with the hardware pins
  OledDisplay miniTV("Mini TV", POT_PIN, BTN_PIN);
  
  // Link to the global pointer so Core 0 can trigger downloads
  pMiniTV = &miniTV; 

  for (;;) {
    OledCommand oc;
    while (xQueueReceive(oledQueue, &oc, 0) == pdTRUE) {
      miniTV.handleCommand(oc.cmdId, oc.payload);
    }
    miniTV.update();
    vTaskDelay(pdMS_TO_TICKS(2)); 
  }
}

void setup() {
  Serial.begin(115200);
  u8g2.begin();
  u8g2.setBusClock(400000);

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(15, 35, "SYSTEM READY");
  u8g2.sendBuffer();

  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS Mount Failed");
    return;
  }

  Serial.println("Files on LittleFS:");
  File root = LittleFS.open("/");
  File file = root.openNextFile();
  while (file) {
    Serial.print(" - ");
    Serial.print(file.name());
    Serial.print(" (");
    Serial.print(file.size());
    Serial.println(" bytes)");
    file = root.openNextFile();
  }

  oledQueue = xQueueCreate(10, sizeof(OledCommand));

  xTaskCreatePinnedToCore(core0Task, "Core0Main", 4096, NULL, 1, NULL, 0);
  
  // Note: We now save the TaskHandle to TaskCore1 so we can suspend it later
  xTaskCreatePinnedToCore(oledTask,  "OledCore1", 4096, NULL, 1, &TaskCore1, 1);
}

void loop() {
  vTaskDelete(NULL); 
}