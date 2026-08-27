#include <Wire.h>
#include <U8g2lib.h>

// --- YOUR VIDEO FILES ---
// (Change "videoframe900.h" to "videoframe.h" if that is what your file is named!)
#include "videoframe900.h" 
#include "videoframe2.h"  

// --- SMART HOME PINS ---
#define BULB1_PIN 13
#define BULB2_PIN 14
#define AUTO_LED_PIN 4

U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, /* reset=*/ U8X8_PIN_NONE);

// Hardware states
bool bulb1State = false;
bool bulb2State = false;

// TV Mode states
bool inTVMode = false;
bool isPlaying = false; 
int currentVideo = 1;   
int currentFrame = 0;

// Re-built showText function using U8g2 instead of Adafruit
void showText(const char* msg) {
  u8g2.clearBuffer();
  u8g2.setDrawColor(1);
  u8g2.setFont(u8g2_font_ncenB08_tr); 
  // Center-ish alignment for popups
  u8g2.drawStr(15, 35, msg);
  u8g2.sendBuffer();
}

void setup() {
  Serial.begin(115200);
  
  // Initialize Pins
  pinMode(BULB1_PIN, OUTPUT);
  pinMode(BULB2_PIN, OUTPUT);
  pinMode(AUTO_LED_PIN, OUTPUT);
  digitalWrite(BULB1_PIN, LOW);
  digitalWrite(BULB2_PIN, LOW);
  digitalWrite(AUTO_LED_PIN, LOW);

  // Initialize Screen
  u8g2.begin();
  u8g2.setBusClock(400000); // Overclock to 400kHz
  
  showText("SYSTEM READY");
}

void loop() {
  // 1. Listen for serial characters sent by your Python ML script
  if (Serial.available()) {
    char cmd = Serial.read();

    switch (cmd) {
      // ---- SMART HOME / LED CONTROLS ----
      case 'A': // Toggle Bulb 1
        bulb1State = !bulb1State;
        digitalWrite(BULB1_PIN, bulb1State ? HIGH : LOW);
        if (!inTVMode) showText(bulb1State ? "BULB 1: ON" : "BULB 1: OFF");
        break;
        
      case 'B': // Toggle Bulb 2
        bulb2State = !bulb2State;
        digitalWrite(BULB2_PIN, bulb2State ? HIGH : LOW);
        if (!inTVMode) showText(bulb2State ? "BULB 2: ON" : "BULB 2: OFF");
        break;
        
      case 'H': // Auto Mode ON
        bulb1State = false;
        bulb2State = false;
        digitalWrite(BULB1_PIN, LOW);
        digitalWrite(BULB2_PIN, LOW);
        digitalWrite(AUTO_LED_PIN, HIGH);
        if (!inTVMode) showText("AUTO ON");
        break;
        
      case 'I': // Auto Mode OFF
        digitalWrite(AUTO_LED_PIN, LOW);
        if (!inTVMode) showText("AUTO OFF");
        break;

      // ---- TV / VIDEO CONTROLS ----
      case 'J': // OK Sign: Enter TV Mode and Play
        inTVMode = true;
        isPlaying = true;
        break;
        
      case 'K': // OK Sign again: Exit TV Mode
        inTVMode = false;
        isPlaying = false;
        showText("TV OFF");
        break;
        
      case 'P': // Open Palm: Play
        if (inTVMode) isPlaying = true;
        break;
        
      case 'Q': // Fist: Pause
        if (inTVMode) isPlaying = false; // Pauses on the current frame
        break;
        
      case 'N': // Thumbs Up: Next Channel
      case 'M': // Thumbs Down: Prev Channel
        if (inTVMode) {
          currentVideo = (currentVideo == 1) ? 2 : 1; 
          currentFrame = 0; 
          isPlaying = true; 
        }
        break;
    }
  }

  // 2. Render the video if TV Mode is active and unpaused
  if (inTVMode && isPlaying) {
    u8g2.clearBuffer();
    
    // Set draw color to WHITE on the default BLACK background
    u8g2.setDrawColor(1);
    
    if (currentVideo == 1) {
      u8g2.drawXBM(0, 0, 128, 64, video_frames[currentFrame]);
      currentFrame++;
      if (currentFrame >= TOTAL_FRAMES) currentFrame = 0; 
    } 
    else if (currentVideo == 2) {
      u8g2.drawXBM(0, 0, 128, 64, video_frames2[currentFrame]);
      currentFrame++;
      if (currentFrame >= TOTAL_FRAMES_2) currentFrame = 0; 
    }
    
    u8g2.sendBuffer();
  }
}