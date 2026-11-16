#include <Arduino.h>
#include <ArduinoJson.h>
#include <Preferences.h>
#include <USB.h>
#include <USBHID.h>
#include <USBHIDKeyboard.h>
#include <USBHIDConsumerControl.h>
#include <Adafruit_ILI9341.h>
#include <esp_heap_caps.h>
#include "touch_input.h"
#include "encoder_clicks.h"
#include "frame_codec.h"

// Pin numbers are GPIO labels, not header positions.
constexpr uint8_t KEYS[] = {4, 5, 6, 7, 8, 9};
constexpr uint8_t CLK = 10, DT = 11, SW = 12;
constexpr uint8_t BACKLIGHT = 18, BACKLIGHT_CHANNEL = 7;
uint8_t brightness = 100, preferredBrightness = 100;
constexpr size_t FRAME_SIZE = 320 * 240 * 2;
constexpr uint32_t RX_TIMEOUT = 12000;
USBHID hid;
USBHIDKeyboard keyboard;
USBHIDConsumerControl consumer;
USBCDC usb;
Preferences prefs;
Adafruit_ILI9341 tft(&SPI, 15, 17, 16);
uint8_t *frame = nullptr, *encodedFrame = nullptr;
bool compressedFrame = false, codecChecksPassed = false;
uint32_t decodedLength = 0, expectedPixelCrc = 0, pixelCrc = 0;
uint32_t frameCount = 0, frameCrc = 0, expectedCrc = 0, sequence = 0;
size_t received = 0;
uint16_t frameX = 0, frameY = 0, frameWidth = 320, frameHeight = 240;
uint32_t expectedLength = FRAME_SIZE;
Stream *owner = nullptr;
uint32_t lastByte = 0, lastFrame = 0;
bool receiving = false, painting = false, displayStale = false;
uint16_t paintRow = 0;
uint8_t actions[6] = {1, 2, 13, 14, 3, 4};
bool invertEncoder = false;
uint8_t encoderSteps = 4;
String inputLines[2];
bool dropLines[2] = {};
TouchInput touchInput;
Stream *eventPort = nullptr;
EncoderClicks encoderClicks;
uint32_t controlCount = 0;
bool encoderChecksPassed = false;

// 0:disabled, 1..12:F13..F24, 13:previous,14:next,15:play,
// 16:system mute,17:volume up,18:volume down.
bool runAction(uint8_t action) {
  if (!action || !hid.ready()) return false;
  if (action <= 12) {
    keyboard.press(KEY_F13 + action - 1);
    delay(12);
    keyboard.releaseAll();
    return true;
  }
  const uint16_t usages[] = {
    CONSUMER_CONTROL_SCAN_PREVIOUS, CONSUMER_CONTROL_SCAN_NEXT,
    CONSUMER_CONTROL_PLAY_PAUSE, CONSUMER_CONTROL_MUTE,
    CONSUMER_CONTROL_VOLUME_INCREMENT, CONSUMER_CONTROL_VOLUME_DECREMENT
  };
  if (action > 18) return false;
  consumer.press(usages[action - 13]);
  delay(8);
  consumer.release();
  return true;
}

void encoderAction(uint8_t action) {
  if (hid.ready()) {runAction(action); return;}
  if (!eventPort) return;
  const char *name = action == 13 ? "previous" : action == 14 ? "next" :
                     action == 15 ? "play_pause" : action == 16 ? "mute" : action == 17 ? "volume_up" :
                     action == 18 ? "volume_down" : nullptr;
  if (name) eventPort->printf("{\"type\":\"control\",\"id\":%lu,\"action\":\"%s\",\"event_ms\":%lu}\n",
                             (unsigned long)++controlCount, name, (unsigned long)millis());
}

struct Button {
  uint8_t pin;
  Button(uint8_t value) : pin(value) {}
  bool raw = HIGH, stable = HIGH;
  uint32_t changed = 0;
  bool pressed() {
    bool now = digitalRead(pin);
    if (raw != now) {raw = now; changed = millis();}
    if (stable != raw && millis() - changed >= 25) {
      stable = raw;
      return stable == LOW && millis() > 800;
    }
    return false;
  }
};
Button buttons[] = {{4}, {5}, {6}, {7}, {8}, {9}, {12}};
uint8_t previousAB = 0;
int8_t encoderDelta = 0;
uint32_t encoderTime = 0;
void scanControls() {
  for (uint8_t i = 0; i < 6; i++)
    if (buttons[i].pressed()) runAction(actions[i]);
  if (!encoderChecksPassed) return;
  bool pressEdge = buttons[6].pressed();
  uint8_t clicks = encoderClicks.update(pressEdge, buttons[6].stable == LOW, millis());
  if (clicks) encoderAction(clicks == 1 ? 15 : clicks == 2 ? 14 : clicks == 3 ? 13 : 16);
  static const int8_t table[16] = {0,-1,1,0, 1,0,0,-1, -1,0,0,1, 0,1,-1,0};
  uint8_t ab = (digitalRead(CLK) << 1) | digitalRead(DT);
  if (ab == previousAB) return;
  if (millis() - encoderTime > 250 || (ab ^ previousAB) == 3) encoderDelta = 0;
  encoderTime = millis();
  encoderDelta += table[(previousAB << 2) | ab];
  previousAB = ab;
  if (abs(encoderDelta) >= encoderSteps) {
    bool positive = encoderDelta > 0;
    encoderAction((positive != invertEncoder) ? 17 : 18);
    encoderDelta = 0;
  }
}

uint32_t crcTable[256];
void crcInit() {
  for (uint32_t i = 0; i < 256; i++) {
    uint32_t c = i;
    for (int j = 0; j < 8; j++) c = (c >> 1) ^ ((c & 1) ? 0xEDB88320 : 0);
    crcTable[i] = c;
  }
}
void error(Stream &port, const char *message) {
  port.printf("{\"type\":\"error\",\"message\":\"%s\"}\n", message);
}
void info(Stream &port) {
  StaticJsonDocument<1024> out;
  out["type"] = "hello"; out["device"] = "MacroDeck";
  out["version"] = "2.0.0"; out["protocol"] = 3; out["chunk_size"] = 4096; out["baud"] = 921600;
  out["rle565"] = codecChecksPassed && encodedFrame != nullptr;
  out["codec_self_test"] = codecChecksPassed;
  out["touch_clock"] = true; out["brightness_persist"] = true;
  out["preferred_brightness"] = preferredBrightness;
  out["brightness"] = brightness; out["backlight_pwm"] = bool(DECK_DISPLAY);
  out["encoder_multiclick"] = true;
  out["encoder_self_test"] = encoderChecksPassed;
  out["touch_enabled"] = bool(DECK_DISPLAY);
  out["width"] = 320; out["height"] = 240;
  out["display_enabled"] = bool(DECK_DISPLAY);
  out["frame_buffer"] = frame != nullptr;
  out["frames"] = frameCount; out["hid_ready"] = hid.ready();
  out["psram"] = ESP.getPsramSize(); out["flash"] = ESP.getFlashChipSize();
  out["heap_free"] = ESP.getFreeHeap(); out["uptime_ms"] = millis();
  out["invert"] = invertEncoder; out["steps"] = encoderSteps;
  auto list = out.createNestedArray("keys");
  for (uint8_t a : actions) list.add(a);
  serializeJson(out, port); port.println();
}
void command(Stream &port, const String &line) {
  StaticJsonDocument<512> doc;
  if (deserializeJson(doc, line)) {error(port, "invalid_json"); return;}
  const char *type = doc["type"] | "";
  if (!strcmp(type, "hello") || !strcmp(type, "ping")) {eventPort = &port; info(port); return;}
  if (!strcmp(type, "brightness")) {
    bool persist = doc["persist"] | false;
    if (!doc["value"].is<uint8_t>() || doc["value"].as<uint8_t>() > 100 ||
        (doc.containsKey("persist") && !doc["persist"].is<bool>()) ||
        (persist && doc["value"].as<uint8_t>() < 5)) {
      error(port,"invalid_brightness"); return;
    }
    brightness = doc["value"];
#if DECK_DISPLAY
    ledcWrite(BACKLIGHT_CHANNEL, (uint32_t(brightness)*255+50)/100);
#endif
    bool saved = true;
    if (persist && brightness != preferredBrightness) {
      saved = prefs.putUChar("backlight",brightness) == 1;
      if (saved) preferredBrightness = brightness;
    }
    port.printf("{\"type\":\"brightness\",\"value\":%u,\"preferred\":%u,\"saved\":%s}\n",brightness,preferredBrightness,saved ? "true" : "false");
    return;
  }
  if (!strcmp(type, "frame")) {
    if (receiving || painting) {error(port, "busy"); return;}
    if (!frame) {error(port, "no_frame_buffer"); return;}
    if (!doc["x"].is<uint16_t>() || !doc["y"].is<uint16_t>() ||
        !doc["w"].is<uint16_t>() || !doc["h"].is<uint16_t>()) {
      error(port, "invalid_rectangle"); return;
    }
    uint16_t x = doc["x"], y = doc["y"], w = doc["w"], h = doc["h"];
    if (!w || !h || uint32_t(x) + w > 320 || uint32_t(y) + h > 240) {
      error(port, "invalid_rectangle"); return;
    }
    uint32_t bytes = uint32_t(w) * h * 2;
    const char *encoding = doc["encoding"] | "raw";
    bool rle = !strcmp(encoding,"rle565");
    if ((strcmp(encoding,"raw") && !rle) ||
        !doc["length"].is<uint32_t>() || !doc["crc"].is<uint32_t>() || !doc["seq"].is<uint32_t>()) {
      error(port,"invalid_frame"); return;
    }
    uint32_t length = doc["length"];
    if (!length || length > FRAME_SIZE || (!rle && length != bytes) ||
        (rle && (!encodedFrame || !codecChecksPassed || !doc["decoded_length"].is<uint32_t>() ||
                 doc["decoded_length"].as<uint32_t>() != bytes || !doc["pixel_crc"].is<uint32_t>()))) {
      error(port,"invalid_frame"); return;
    }
    sequence = doc["seq"]; expectedCrc = doc["crc"];
    frameX = x; frameY = y; frameWidth = w; frameHeight = h; expectedLength = length;
    decodedLength = bytes; compressedFrame = rle;
    expectedPixelCrc = rle ? doc["pixel_crc"].as<uint32_t>() : expectedCrc;
    frameCrc = 0xFFFFFFFF; received = 0; owner = &port;
    receiving = true; lastByte = millis();
    port.printf("{\"type\":\"ready\",\"seq\":%lu}\n", (unsigned long)sequence);
    return;
  }
  if (!strcmp(type, "config")) {
    if (!doc["keys"].is<JsonArray>() || doc["keys"].size() != 6 ||
        !doc["invert"].is<bool>() || !doc["steps"].is<uint8_t>() ||
        (doc["steps"] != 2 && doc["steps"] != 4)) {error(port, "invalid_config"); return;}
    uint8_t next[6];
    for (int i = 0; i < 6; i++) {
      if (!doc["keys"][i].is<uint8_t>() || doc["keys"][i].as<uint8_t>() > 18) {
        error(port, "invalid_action"); return;
      }
      next[i] = doc["keys"][i];
    }
    bool invert = doc["invert"], changed = memcmp(next, actions, 6) || invert != invertEncoder || encoderSteps != doc["steps"].as<uint8_t>();
    memcpy(actions, next, 6); invertEncoder = invert; encoderSteps = doc["steps"];
    if (changed) {
      prefs.putBytes("keys", actions, 6); prefs.putBool("invert", invertEncoder);
      prefs.putUChar("steps", encoderSteps);
    }
    port.println("{\"type\":\"configured\"}"); return;
  }
  error(port, "unknown_command");
}
void pollPort(Stream &port, uint8_t index) {
  if (painting) return;
  if (receiving && owner != &port) return;
  size_t budget = 1024;
  while (port.available() && budget--) {
    int b = port.read(); if (b < 0) break;
    if (receiving) {
      (compressedFrame ? encodedFrame : frame)[received++] = b;
      frameCrc = crcTable[(frameCrc ^ b) & 0xFF] ^ (frameCrc >> 8);
      lastByte = millis();
      if (received % 4096 == 0 || received == expectedLength)
        port.printf("{\"type\":\"chunk\",\"seq\":%lu,\"offset\":%u}\n",
                    (unsigned long)sequence, (unsigned)received);
      if (received == expectedLength) {
        receiving = false;
        if ((frameCrc ^ 0xFFFFFFFF) != expectedCrc) {
          error(port, "crc_mismatch"); owner = nullptr;
        } else {
          bool valid = !compressedFrame || decodeRle565(encodedFrame,expectedLength,frame,decodedLength);
          pixelCrc = 0xFFFFFFFF;
          if (valid) for (uint32_t i = 0; i < decodedLength; i++)
            pixelCrc = crcTable[(pixelCrc ^ frame[i]) & 0xFF] ^ (pixelCrc >> 8);
          pixelCrc ^= 0xFFFFFFFF;
          if (!valid || pixelCrc != expectedPixelCrc) {
            error(port, valid ? "pixel_crc_mismatch" : "invalid_rle"); owner = nullptr;
          } else {painting = true; paintRow = 0;}
        }
        break;
      }
    } else if (b == '\n') {
      if (!dropLines[index] && inputLines[index].length()) command(port, inputLines[index]);
      inputLines[index] = ""; dropLines[index] = false;
    } else if (b != '\r' && !dropLines[index]) {
      if (inputLines[index].length() < 511) inputLines[index] += char(b);
      else {dropLines[index] = true; error(port, "header_too_long");}
    }
  }
}

#if DECK_DISPLAY
void drawLinkWaiting() {
  tft.fillScreen(0x1063);
  tft.fillRect(16,25,288,3,0xFA6A);
  tft.setTextColor(ILI9341_WHITE); tft.setTextSize(3); tft.setCursor(16,50);
  tft.print("MacroDeck");
  tft.setTextSize(2); tft.setCursor(16,109); tft.print("Bilgisayar baglantisi");
  tft.setCursor(16,133); tft.print("bekleniyor");
  tft.setTextSize(1); tft.setCursor(16,180);
  tft.print("Uygulamayi acin veya USB'yi kontrol edin.");
}
#endif

void setup() {
  Serial.setRxBufferSize(8192); Serial.begin(921600);
  encoderChecksPassed = encoderClicksSelfTest();
  codecChecksPassed = frameCodecSelfTest();
  for (uint8_t pin : KEYS) pinMode(pin, INPUT_PULLUP);
  pinMode(CLK, INPUT_PULLUP); pinMode(DT, INPUT_PULLUP); pinMode(SW, INPUT_PULLUP);
  previousAB = (digitalRead(CLK) << 1) | digitalRead(DT);
  crcInit();
  frame = (uint8_t *)heap_caps_malloc(FRAME_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  encodedFrame = (uint8_t *)heap_caps_malloc(FRAME_SIZE, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
  prefs.begin("macrodeck", false);
  preferredBrightness = prefs.getUChar("backlight",100);
  if (preferredBrightness < 5 || preferredBrightness > 100) preferredBrightness = 100;
  brightness = preferredBrightness;
  uint8_t stored[6];
  if (prefs.getBytesLength("keys") == 6) {
    prefs.getBytes("keys", stored, 6);
    bool valid = true; for (uint8_t a : stored) if (a > 18) valid = false;
    if (valid) memcpy(actions, stored, 6);
  }
  invertEncoder = prefs.getBool("invert", false);
  encoderSteps = prefs.getUChar("steps", 4);
  if (encoderSteps != 2 && encoderSteps != 4) encoderSteps = 4;
  usb.setRxBufferSize(8192); usb.setTxTimeoutMs(50); usb.enableReboot(false);
  usb.begin(); keyboard.begin(); consumer.begin();
  USB.productName("MacroDeck Media"); USB.manufacturerName("DIY MacroDeck");
  USB.serialNumber("MacroDeck-N16R8-01"); USB.begin();
#if DECK_DISPLAY
  SPI.begin(14, -1, 13, 17); // LCD MISO is unconnected; GPIO18 now drives backlight.
  tft.begin(10000000); tft.setRotation(1); tft.fillScreen(ILI9341_BLACK);
  drawLinkWaiting();
  touchInput.begin();
  ledcSetup(BACKLIGHT_CHANNEL, 5000, 8);
  ledcAttachPin(BACKLIGHT, BACKLIGHT_CHANNEL);
  ledcWrite(BACKLIGHT_CHANNEL, (uint32_t(brightness)*255+50)/100);
#endif
  Serial.println(); info(Serial);
}
void loop() {
  scanControls(); pollPort(usb, 0); pollPort(Serial, 1);
#if DECK_DISPLAY
  touchInput.poll(eventPort);
#endif
  if (receiving && millis() - lastByte > RX_TIMEOUT) {
    receiving = false; error(*owner, "frame_timeout"); owner = nullptr;
  }
  if (painting) {
    uint16_t rows = min(uint16_t(8), uint16_t(frameHeight - paintRow));
#if DECK_DISPLAY
    // RGB565 little-endian words; draw in short strips so buttons keep scanning.
    tft.drawRGBBitmap(frameX, frameY + paintRow,
                      (uint16_t *)(frame + paintRow * frameWidth * 2), frameWidth, rows);
#endif
    paintRow += rows;
    if (paintRow == frameHeight) {
      painting = false; ++frameCount; lastFrame = millis(); displayStale = false;
      owner->printf("{\"type\":\"ack\",\"seq\":%lu,\"frames\":%lu,\"pixel_crc\":%lu}\n",
                    (unsigned long)sequence, (unsigned long)frameCount, (unsigned long)pixelCrc);
      owner = nullptr;
    }
  }
#if DECK_DISPLAY
  if (!receiving && !painting && frameCount && !displayStale && millis() - lastFrame > 15000) {
    drawLinkWaiting(); displayStale = true;
  }
#endif
  delay(1);
}
