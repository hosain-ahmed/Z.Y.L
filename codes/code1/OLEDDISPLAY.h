#ifndef OLEDDISPLAY_H
#define OLEDDISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include <LittleFS.h>
#include "SMARTDEVICE.h"

extern U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2;

enum class TVState { OFF, PLAYING, PAUSED };

class OledDisplay : public SmartDevice {
  private:
    TVState state;
    File vidFile;
    int currentVideo;      // 1 or 2 for now, hardcoded filenames
    const char* name;

  public:
    OledDisplay(const char* deviceName) {
      name = deviceName;
      state = TVState::OFF;
      currentVideo = 1;
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      switch (cmdId) {
        case 0x05: // CMD_TV_ON
          openCurrentVideo();
          state = TVState::PLAYING;
          break;
        case 0x06: // CMD_TV_OFF
          state = TVState::OFF;
          if (vidFile) vidFile.close();
          showMessage("TV OFF");
          break;
        case 0x07: // CMD_TV_PLAY
          if (state != TVState::OFF) state = TVState::PLAYING;
          break;
        case 0x08: // CMD_TV_PAUSE
          if (state != TVState::OFF) state = TVState::PAUSED;
          break;
        case 0x09: // CMD_TV_NEXT
        case 0x0A: // CMD_TV_PREV
          if (state != TVState::OFF) {
            currentVideo = (currentVideo == 1) ? 2 : 1;
            openCurrentVideo();
            state = TVState::PLAYING;
          }
          break;
      }
    }

    void update() override {
      if (state != TVState::PLAYING) return;
      if (!vidFile) return;

      static uint8_t frameBuffer[1024];
      size_t bytesRead = vidFile.read(frameBuffer, 1024);

      if (bytesRead < 1024) {
        // reached end of file — loop back to the start
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

    const char* getName() override { return name; }

  private:
    void openCurrentVideo() {
      if (vidFile) vidFile.close();
      String path = "/video" + String(currentVideo) + ".bin";
      vidFile = LittleFS.open(path, "r");
      if (!vidFile) {
        showMessage("FILE OPEN FAIL");
      }
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