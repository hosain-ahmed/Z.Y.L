#include <Wire.h>
#include <U8g2lib.h>
#include <SPI.h>
#include <SD.h>

// Initialize OLED (Standard I2C pins 21 & 22)
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

const int SD_CS_PIN = 5;
File videoFile;
uint8_t frameBuffer[1024]; // 128x64 / 8 = 1024 bytes per frame

void setup() {
  Serial.begin(115200);
  
  // 1. Initialize Display
  u8g2.begin();
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(0, 30, "Init SD Card...");
  u8g2.sendBuffer();

  // 2. Initialize SD Card
  if (!SD.begin(SD_CS_PIN)) {
    Serial.println("SD Card Mount Failed!");
    u8g2.clearBuffer();
    u8g2.drawStr(0, 30, "SD Failed!");
    u8g2.sendBuffer();
    return;
  }

  // 3. Open Video File
  videoFile = SD.open("/video.bin");
  if (!videoFile) {
    Serial.println("Failed to open /video.bin");
    u8g2.clearBuffer();
    u8g2.drawStr(0, 30, "File Not Found!");
    u8g2.sendBuffer();
    return;
  }
}

void loop() {
  if (videoFile) {
    // Read one full frame (1024 bytes) into the buffer
    if (videoFile.read(frameBuffer, 1024) == 1024) {
      
      u8g2.clearBuffer();
      // Draw the frame buffer to the OLED
      u8g2.drawXBM(0, 0, 128, 64, frameBuffer);
      u8g2.sendBuffer();
      
    } else {
      // Reached the end of the file, loop back to the beginning
      videoFile.seek(0);
    }
  }
}