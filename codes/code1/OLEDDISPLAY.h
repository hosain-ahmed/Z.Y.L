#ifndef OLEDDISPLAY_H
#define OLEDDISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include "SMARTDEVICE.h"
#include "videoframe900.h" 
#include "videoframe2.h"

extern U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2;

enum class TVState { OFF, PLAYING, PAUSED };

class OledDisplay : public SmartDevice {
  private:
    TVState state;
    int currentVideo;
    int currentFrame;
    const char* name;

  public:
    OledDisplay(const char* deviceName) {
      name = deviceName;
      state = TVState::OFF;
      currentVideo = 1;
      currentFrame = 0;
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      switch (cmdId) {
        case 0x05: // CMD_TV_ON
          state = TVState::PLAYING;
          break;
        case 0x06: // CMD_TV_OFF
          state = TVState::OFF;
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
            currentFrame = 0;
            state = TVState::PLAYING;
          }
          break;
      }
    }

    void update() override {
      if (state != TVState::PLAYING) return;  // only render when actively playing

      u8g2.clearBuffer();
      u8g2.setDrawColor(1);

      if (currentVideo == 1) {
        u8g2.drawXBM(0, 0, 128, 64, video_frames[currentFrame]);
        currentFrame = (currentFrame + 1) % TOTAL_FRAMES;
      } else {
        u8g2.drawXBM(0, 0, 128, 64, video_frames2[currentFrame]);
        currentFrame = (currentFrame + 1) % TOTAL_FRAMES_2;
      }

      u8g2.sendBuffer();
    }

    const char* getName() override { return name; }

  private:
    void showMessage(const char* msg) {
      u8g2.clearBuffer();
      u8g2.setDrawColor(1);
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(15, 35, msg);
      u8g2.sendBuffer();
    }
};

#endif