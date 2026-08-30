#include <Wire.h>
#include <U8g2lib.h>
#include <LittleFS.h>

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

void setup() {
  Serial.begin(115200);
  delay(1000);

  u8g2.begin();
  u8g2.setBusClock(400000);

  // --- Mount LittleFS, format if it's never been formatted before ---
  if (!LittleFS.begin(true)) {
    Serial.println("LittleFS mount FAILED.");
    showMessage("LFS MOUNT FAIL");
    while (true) delay(1000);
  }
  Serial.println("LittleFS mounted OK.");
  showMessage("LFS MOUNTED OK");
  delay(1000);

  // --- Wait for the Python script to say it's ready to send ---
  Serial.println("READY_FOR_FILE");
  while (!Serial.available()) delay(10);

  // --- Read 4-byte little-endian file size ---
  uint8_t sizeBytes[4];
  Serial.readBytes(sizeBytes, 4);
  uint32_t fileSize = sizeBytes[0] | (sizeBytes[1] << 8) | (sizeBytes[2] << 16) | (sizeBytes[3] << 24);
  Serial.printf("Expecting %lu bytes...\n", fileSize);

  // --- Write incoming bytes to /test.bin ---
  File f = LittleFS.open("/test.bin", "w");
  if (!f) {
    Serial.println("Failed to open /test.bin for writing.");
    showMessage("OPEN WRITE FAIL");
    while (true) delay(1000);
  }

  uint32_t received = 0;
  uint8_t buf[128];
  while (received < fileSize) {
    size_t toRead = min((uint32_t)128, fileSize - received);
    size_t got = Serial.readBytes(buf, toRead);
    if (got > 0) {
      f.write(buf, got);
      received += got;
      Serial.printf("Progress: %lu/%lu\n", received, fileSize);
      Serial.println("ACK");  // tell Python it's safe to send the next chunk
    } else {
      Serial.println("TIMEOUT_NO_DATA");  // surfaces stalls instead of hanging silently
    }
  }
  f.close();
  Serial.println("File write complete.");
  showMessage("FILE SAVED");
  delay(1000);

  // --- Now read it back and confirm size matches ---
  File check = LittleFS.open("/test.bin", "r");
  Serial.printf("Read-back file size: %d bytes (expected %lu)\n", check.size(), fileSize);
  check.close();
}

void loop() {
  // --- Play the saved file on loop, 1024 bytes per frame ---
  static File vidFile;
  static bool opened = false;

  if (!opened) {
    vidFile = LittleFS.open("/test.bin", "r");
    if (!vidFile) {
      showMessage("PLAYBACK OPEN FAIL");
      delay(2000);
      return;
    }
    opened = true;
  }

  uint8_t frameBuffer[1024];
  size_t bytesRead = vidFile.read(frameBuffer, 1024);

  if (bytesRead < 1024) {
    // reached end of file, loop back to start
    vidFile.seek(0);
    bytesRead = vidFile.read(frameBuffer, 1024);
    if (bytesRead < 1024) {
      showMessage("FRAME READ FAIL");
      delay(2000);
      return;
    }
  }

  u8g2.clearBuffer();
  u8g2.setDrawColor(1);
  u8g2.drawXBM(0, 0, 128, 64, frameBuffer);
  u8g2.sendBuffer();

  // delay(50);  // ~20fps test playback pace
}

void showMessage(const char* msg) {
  u8g2.clearBuffer();
  u8g2.setDrawColor(1);
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(5, 35, msg);
  u8g2.sendBuffer();
}
