#ifndef OLEDDISPLAY_H
#define OLEDDISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include <LittleFS.h>
#include "SMARTDEVICE.h"

extern U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2;

// --- NEW FIX: Added DOWNLOADING state ---
enum class TVState { OFF, PLAYING, PAUSED, MENU, DOWNLOADING };

class OledDisplay : public SmartDevice {
  private:
    TVState state;
    File vidFile;
    const char* name;

    // Hardware Pins
    int potPin;
    int btnPin;
    bool lastBtnState;
    unsigned long lastBtnTime; // --- NEW FIX: Button debounce timer ---

    // Media Server Data
    String videoList[10];      
    int totalVideos;

    // Caching System
    String cachedNames[2];     
    int lruSlot;               

  public:
    OledDisplay(const char* deviceName, int potentiometerPin, int buttonPin) {
      name = deviceName;
      state = TVState::MENU;   
      potPin = potentiometerPin;
      btnPin = buttonPin;
      lastBtnState = HIGH;
      lastBtnTime = 0;
      totalVideos = 0;
      lruSlot = 0; 
      
      cachedNames[0] = "";
      cachedNames[1] = "";

      pinMode(btnPin, INPUT_PULLUP);
    }

    void addVideoToList(String videoName) {
      if (totalVideos < 10) {
        videoList[totalVideos] = videoName;
        totalVideos++;
      }
    }

    void cacheDownloadComplete(String videoName) {
      cachedNames[lruSlot] = videoName;
      
      String path = "/slot" + String(lruSlot) + ".bin";
      openVideoFile(path);
      
      lruSlot = (lruSlot == 0) ? 1 : 0; 
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      switch (cmdId) {
        case 0x05: // CMD_TV_ON
          state = TVState::MENU;
          break;
        case 0x06: // CMD_TV_OFF
          state = TVState::OFF;
          showMessage("TV OFF");
          break;
        case 0x07: // CMD_TV_PLAY
          if (state == TVState::PAUSED) state = TVState::PLAYING;
          break;
        case 0x08: // CMD_TV_PAUSE
          if (state == TVState::PLAYING) state = TVState::PAUSED;
          break;
      }
    }

    void update() override {
      if (state == TVState::OFF) return;

      if (state == TVState::MENU) {
        drawMenuAndHandleInputs();
      } else if (state == TVState::PLAYING) {
        streamVideoFrame();
      }
      // If state is DOWNLOADING, we intentionally do nothing so the "DOWNLOADING..." text stays on screen!
    }

    const char* getName() override { return name; }

  private:
    void drawMenuAndHandleInputs() {
      if (totalVideos == 0) {
        showMessage("AWAITING PC SYNC");
        return;
      }

      int potVal = analogRead(potPin); 
      int selectedIdx = map(potVal, 0, 4095, 0, totalVideos - 1);
      
      if (selectedIdx < 0) selectedIdx = 0;
      if (selectedIdx >= totalVideos) selectedIdx = totalVideos - 1;

      u8g2.clearBuffer();
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(10, 15, "--- SELECT VIDEO ---");
      u8g2.setCursor(10, 40);
      u8g2.print("> ");
      u8g2.print(videoList[selectedIdx]);
      u8g2.sendBuffer();

      bool currentBtn = digitalRead(btnPin);
      
      // --- NEW FIX: 250ms Debounce limit to prevent multiple rapid-fire clicks ---
      if (currentBtn == LOW && lastBtnState == HIGH && millis() - lastBtnTime > 250) {
        lastBtnTime = millis();
        selectVideo(videoList[selectedIdx]);
      }
      lastBtnState = currentBtn;
    }

    void selectVideo(String targetName) {
      if (cachedNames[0] == targetName) {
        openVideoFile("/slot0.bin");
      } 
      else if (cachedNames[1] == targetName) {
        openVideoFile("/slot1.bin");
      } 
      else {
        // --- NEW FIX: Lock the system state into DOWNLOADING ---
        state = TVState::DOWNLOADING; 
        showMessage("DOWNLOADING...");
        Serial.print("FETCH:");
        Serial.println(targetName);
      }
    }

    void openVideoFile(String path) {
      if (vidFile) vidFile.close();
      vidFile = LittleFS.open(path, "r");
      if (vidFile) {
        state = TVState::PLAYING;
      } else {
        showMessage("FILE ERROR");
      }
    }

    void streamVideoFrame() {
      if (!vidFile) return;

      // --- NEW: Click button while playing to exit to menu ---
      bool currentBtn = digitalRead(btnPin);
      if (currentBtn == LOW && lastBtnState == HIGH && millis() - lastBtnTime > 250) {
        lastBtnTime = millis();
        state = TVState::MENU;
        return; // Exit the function instantly without drawing a frame
      }
      lastBtnState = currentBtn;
      // -------------------------------------------------------

      static uint8_t frameBuffer[1024];
      size_t bytesRead = vidFile.read(frameBuffer, 1024);
      
      if (bytesRead < 1024) {
        vidFile.seek(0);
        vidFile.read(frameBuffer, 1024);
      }

      u8g2.clearBuffer();
      u8g2.setDrawColor(1);
      u8g2.drawXBM(0, 0, 128, 64, frameBuffer);
      u8g2.sendBuffer();
    }

    void showMessage(const char* msg) {
      u8g2.clearBuffer();
      u8g2.setDrawColor(1);
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(10, 35, msg);
      u8g2.sendBuffer();
    }
};

#endif