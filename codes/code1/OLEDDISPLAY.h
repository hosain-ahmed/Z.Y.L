#ifndef OLEDDISPLAY_H
#define OLEDDISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include <LittleFS.h>
#include "SMARTDEVICE.h"

extern U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2;

enum class TVState { OFF, MENU, PLAYING, PAUSED };

class OledDisplay : public SmartDevice {
  private:
    TVState state;
    File vidFile;
    int currentVideo;          // 1 or 2, hardcoded for now
    const char* name;

    // Hardware input
    int potPin;
    int btnPin;
    bool lastBtnState;
    unsigned long lastBtnTime;

    // Hardcoded video list (menu display names) — replace with real list in Step 4
    static const int NUM_VIDEOS = 2;
    const char* videoNames[NUM_VIDEOS] = { "Video 1", "Video 2" };

  public:
    OledDisplay(const char* deviceName, int potentiometerPin, int buttonPin) {
      name = deviceName;
      state = TVState::OFF;
      currentVideo = 1;
      potPin = potentiometerPin;
      btnPin = buttonPin;
      lastBtnState = HIGH;
      lastBtnTime = 0;

      pinMode(btnPin, INPUT_PULLUP);
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      switch (cmdId) {
        case 0x05: // CMD_TV_ON -> go to menu, not straight to playing
          state = TVState::MENU;
          break;
        case 0x06: // CMD_TV_OFF
          state = TVState::OFF;
          if (vidFile) vidFile.close();
          showMessage("TV OFF");
          break;
        case 0x07: // CMD_TV_PLAY
          if (state == TVState::PAUSED) state = TVState::PLAYING;
          break;
        case 0x08: // CMD_TV_PAUSE
          if (state == TVState::PLAYING) state = TVState::PAUSED;
          break;
        case 0x09: // CMD_TV_NEXT
        case 0x0A: // CMD_TV_PREV
          // Quick-switch while already playing/paused (legacy gesture shortcut)
          if (state == TVState::PLAYING || state == TVState::PAUSED) {
            currentVideo = (currentVideo == 1) ? 2 : 1;
            openCurrentVideo();
            state = TVState::PLAYING;
          }
          break;
      }
    }

    void update() override {
      switch (state) {
        case TVState::MENU:
          runMenu();
          break;
        case TVState::PLAYING:
          checkExitButton();
          if (state == TVState::PLAYING) streamFrame();  // may have changed to MENU above
          break;
        default:
          break; // OFF, PAUSED -> render nothing new
      }
    }

    const char* getName() override { return name; }

  private:
    void runMenu() {
      int potVal = analogRead(potPin); // 0-4095 on ESP32 ADC
      int selectedIdx = map(potVal, 0, 4095, 0, NUM_VIDEOS - 1);
      if (selectedIdx < 0) selectedIdx = 0;
      if (selectedIdx >= NUM_VIDEOS) selectedIdx = NUM_VIDEOS - 1;

      u8g2.clearBuffer();
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(10, 15, "-- SELECT VIDEO --");
      u8g2.setCursor(10, 40);
      u8g2.print("> ");
      u8g2.print(videoNames[selectedIdx]);
      u8g2.sendBuffer();

      bool currentBtn = digitalRead(btnPin);
      if (currentBtn == LOW && lastBtnState == HIGH && millis() - lastBtnTime > 250) {
        lastBtnTime = millis();
        currentVideo = selectedIdx + 1;  // videoNames[0] -> video1.bin, etc.
        openCurrentVideo();
        state = TVState::PLAYING;
      }
      lastBtnState = currentBtn;
    }

    void checkExitButton() {
      bool currentBtn = digitalRead(btnPin);
      if (currentBtn == LOW && lastBtnState == HIGH && millis() - lastBtnTime > 250) {
        lastBtnTime = millis();
        state = TVState::MENU;
        if (vidFile) vidFile.close();
      }
      lastBtnState = currentBtn;
    }

    void openCurrentVideo() {
      if (vidFile) vidFile.close();
      String path = "/video" + String(currentVideo) + ".bin";
      vidFile = LittleFS.open(path, "r");
      if (!vidFile) {
        showMessage("FILE OPEN FAIL");
      }
    }

    void streamFrame() {
      if (!vidFile) return;

      static uint8_t frameBuffer[1024];
      size_t bytesRead = vidFile.read(frameBuffer, 1024);

      if (bytesRead < 1024) {
        vidFile.seek(0);
        bytesRead = vidFile.read(frameBuffer, 1024);
        if (bytesRead < 1024) {
          showMessage("FRAME READ FAIL");
          return;
        }
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
      u8g2.drawStr(15, 35, msg);
      u8g2.sendBuffer();
    }
};

#endif