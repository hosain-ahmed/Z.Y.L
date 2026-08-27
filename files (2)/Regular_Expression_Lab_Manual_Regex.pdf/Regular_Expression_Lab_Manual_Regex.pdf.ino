#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

#define BULB1_PIN 13
#define BULB2_PIN 14
#define AUTO_LED_PIN 4

#define SCREEN_WIDTH 128
#define SCREEN_HEIGHT 64
Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, -1);

bool bulb1State = false;
bool bulb2State = false;
bool tvPlaying = false;
int channel = 1;
const int NUM_CHANNELS = 3; // placeholder — bump this once you have real content

void updateTVDisplay() {
  display.clearDisplay();
  display.setTextSize(2);
  display.setCursor(0, 0);
  display.println("TV MODE");
  display.setTextSize(1);
  display.print("Channel: "); display.println(channel);
  display.print("Status: "); display.println(tvPlaying ? "PLAY" : "PAUSE");
  display.display();
}

void setup() {
  Serial.begin(115200);
  pinMode(BULB1_PIN, OUTPUT);
  pinMode(BULB2_PIN, OUTPUT);
  pinMode(AUTO_LED_PIN, OUTPUT);
  digitalWrite(BULB1_PIN, LOW);
  digitalWrite(BULB2_PIN, LOW);
  digitalWrite(AUTO_LED_PIN, LOW);

  if (!display.begin(SSD1306_SWITCHCAPVCC, 0x3C)) {
    Serial.println("OLED init failed");
  }
  display.clearDisplay();
  display.display();
}

void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();
    switch (cmd) {
      case 'A':
        bulb1State = !bulb1State;
        digitalWrite(BULB1_PIN, bulb1State ? HIGH : LOW);
        break;
      case 'B':
        bulb2State = !bulb2State;
        digitalWrite(BULB2_PIN, bulb2State ? HIGH : LOW);
        break;
      case 'H': // AUTO enter — force everything off, light indicator
        bulb1State = false;
        bulb2State = false;
        digitalWrite(BULB1_PIN, LOW);
        digitalWrite(BULB2_PIN, LOW);
        digitalWrite(AUTO_LED_PIN, HIGH);
        break;
      case 'I': // AUTO exit
        digitalWrite(AUTO_LED_PIN, LOW);
        break;
      case 'J': // TV mode enter
        tvPlaying = true;
        channel = 1;
        updateTVDisplay();
        break;
      case 'K': // TV mode exit
        display.clearDisplay();
        display.display();
        break;
      case 'P':
        tvPlaying = true;
        updateTVDisplay();
        break;
      case 'Q':
        tvPlaying = false;
        updateTVDisplay();
        break;
      case 'N':
        channel = (channel % NUM_CHANNELS) + 1;
        updateTVDisplay();
        break;
      case 'M':
        channel = ((channel - 2 + NUM_CHANNELS) % NUM_CHANNELS) + 1;
        updateTVDisplay();
        break;
      // 'C' and 'D' (fan) intentionally ignored — no fan wired this phase
    }
  }
}