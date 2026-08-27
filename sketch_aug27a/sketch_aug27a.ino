#include <Wire.h>
#include <U8g2lib.h>
#include "videoframe2.h" // Your giant PROGMEM array

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

int currentFrame = 0;

void setup() {
  Serial.begin(115200);
  u8g2.begin();
}

void loop() {
  u8g2.clearBuffer();
  
  // Use video_frames2 instead of video_frames
  u8g2.drawXBM(0, 0, 128, 64, video_frames2[currentFrame]);
  u8g2.sendBuffer();

  currentFrame++;
  
  // Use TOTAL_FRAMES_2 instead of TOTAL_FRAMES
  if (currentFrame >= TOTAL_FRAMES_2) {
    currentFrame = 0;
  }

  // delay(33); // adjust frame rate delay as needed
}

