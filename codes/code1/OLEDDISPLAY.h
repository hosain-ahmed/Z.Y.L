#ifndef OLEDDISPLAY_H
#define OLEDDISPLAY_H

#include <Arduino.h>
#include <U8g2lib.h>
#include <LittleFS.h>
#include "SMARTDEVICE.h"

extern U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2;

enum class TVState { OFF, MENU, PLAYING, PAUSED, DOWNLOADING };

class OledDisplay : public SmartDevice {
  private:
    TVState state;
    File vidFile;
    const char* name;

    int potPin;
    int btnPin;
    bool lastBtnState;
    unsigned long lastBtnTime;

    static const int MAX_VIDEOS = 10;
    String videoList[MAX_VIDEOS];
    int totalVideos;

    // Cross-core download request — Core 1 sets this, Core 0 polls it.
    volatile bool downloadRequested;
    String pendingFilename;
    String currentFilename;
    int currentIndex;

    // --- ADDED CACHE TRACKERS ---
    String slot1 = ""; // Newest/currently playing video
    String slot2 = ""; // Older cached video

  public:
    OledDisplay(const char* deviceName, int potentiometerPin, int buttonPin) {
      name = deviceName;
      state = TVState::OFF;
      potPin = potentiometerPin;
      btnPin = buttonPin;
      lastBtnState = HIGH;
      lastBtnTime = 0;
      totalVideos = 0;
      currentIndex = 0;
      downloadRequested = false;
      pinMode(btnPin, INPUT_PULLUP);
    }

    // Called by core0Task (with Core1 suspended) when a sync packet arrives
    void addVideoToList(const String &videoName) {
      if (totalVideos < MAX_VIDEOS) {
        videoList[totalVideos] = videoName;
        totalVideos++;
      }
    }

    // Polled by core0Task's main loop every iteration
    bool isDownloadRequested() { return downloadRequested; }
    String getPendingFilename() { return pendingFilename; }

    // Called by core0Task once the file has been fully written (Core1 still suspended)
    void onDownloadComplete(const String &filename) {
      downloadRequested = false;
      currentFilename = filename;
      openCurrentVideo();
      state = TVState::PLAYING;
    }

    void onDownloadFailed() {
      downloadRequested = false;
      state = TVState::MENU;
      showMessage("DOWNLOAD FAILED");
    }

    void handleCommand(uint8_t cmdId, uint8_t payload) override {
      switch (cmdId) {
        case 0x05: // CMD_TV_ON
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
          gestureSkip(1);
          break;
        case 0x0A: // CMD_TV_PREV
          gestureSkip(-1);
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
          if (state == TVState::PLAYING) streamFrame();
          break;
        case TVState::DOWNLOADING:
          // Intentionally do nothing — "DOWNLOADING..." stays on screen
          break;
        default:
          break;
      }
    }

    const char* getName() override { return name; }

  private:
    void runMenu() {
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
      u8g2.drawStr(10, 15, "-- SELECT VIDEO --");
      u8g2.setCursor(10, 40);
      u8g2.print("> ");
      u8g2.print(videoList[selectedIdx]);
      u8g2.sendBuffer();

      bool currentBtn = digitalRead(btnPin);
      if (currentBtn == LOW && lastBtnState == HIGH && millis() - lastBtnTime > 250) {
        lastBtnTime = millis();
        currentIndex = selectedIdx;
        selectVideo(videoList[selectedIdx]);
      }
      lastBtnState = currentBtn;
    }

    // Gesture-driven next/prev
    void gestureSkip(int direction) {
      if (totalVideos == 0) return;
      currentIndex = (currentIndex + direction + totalVideos) % totalVideos;
      selectVideo(videoList[currentIndex]);
    }

    // --- CACHE MANAGEMENT: Automatically delete older videos to save space ---
    void makeSpaceFor(String newFilename) {
      if (slot1 == newFilename) return; // Already newest, do nothing
      
      if (slot2 == newFilename) {
        // Playing the older file again, swap order
        slot2 = slot1;
        slot1 = newFilename;
        return;
      }

      // Brand new file. Delete the oldest one (slot2) from flash
      if (slot2 != "") {
        String pathToEvict = "/" + slot2;
        if (LittleFS.exists(pathToEvict)) {
          LittleFS.remove(pathToEvict);
          Serial.println("EVICTED: " + pathToEvict);
        }
      }

      // Shift history down
      slot2 = slot1;
      slot1 = newFilename;
    }

    void selectVideo(const String &targetName) {
      // 1. Clear space before doing anything else!
      makeSpaceFor(targetName); 
      
      String path = "/" + targetName;
      if (LittleFS.exists(path)) {
        currentFilename = targetName;
        openCurrentVideo();
        state = TVState::PLAYING;
      } else {
        state = TVState::DOWNLOADING;
        showMessage("DOWNLOADING...");
        pendingFilename = targetName;
        downloadRequested = true;  // core0Task will notice this and take over
      }
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
      String path = "/" + currentFilename;
      vidFile = LittleFS.open(path, "r");
      if (!vidFile) showMessage("FILE OPEN FAIL");
    }

    void streamFrame() {
      if (!vidFile) return;
      static uint8_t frameBuffer[1024];
      size_t bytesRead = vidFile.read(frameBuffer, 1024);
      
      if (bytesRead < 1024) {
        vidFile.seek(0); // loop to beginning
        bytesRead = vidFile.read(frameBuffer, 1024);
        if (bytesRead < 1024) { showMessage("FRAME READ FAIL"); return; }
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