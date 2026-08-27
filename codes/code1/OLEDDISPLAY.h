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

    void handleCommand(char cmd) override {
      switch (cmd) {
        case 'J': // enter TV mode, start playing
          state = TVState::PLAYING;
          break;
        case 'K': // exit TV mode
          state = TVState::OFF;
          showMessage("TV OFF");
          break;
        case 'P': // play
          if (state != TVState::OFF) state = TVState::PLAYING;
          break;
        case 'Q': // pause
          if (state != TVState::OFF) state = TVState::PAUSED;
          break;
        case 'N':
        case 'M':
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