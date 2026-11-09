#pragma once
#include <stdint.h>
#include <vector>
#include "SPI.h"

#define INITR_MINI160x80 0x04
#define INITR_MINI160x80_PLUGIN 0x06

struct Adafruit_ST7735 {
  Adafruit_ST7735(SPIClass *, int8_t, int8_t, int8_t) {}
  void initR(uint8_t) {}
  void setSPISpeed(uint32_t) {}
  void setRotation(uint8_t r) { rotation = r; }
  void invertDisplay(bool i) { inverted = i; }
  void fillScreen(uint16_t) {}
  void drawRGBBitmap(int16_t, int16_t, uint16_t *pix, int16_t w, int16_t h) {
    last.assign(pix, pix + (size_t)w * h);
    present_count++;
  }
  uint8_t rotation = 0;
  bool inverted = false;
  int present_count = 0;
  std::vector<uint16_t> last;
};
