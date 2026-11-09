#pragma once
#include <stdint.h>
#include <vector>
#include "SPI.h"

struct Adafruit_ST7789 {
  Adafruit_ST7789(SPIClass *, int8_t, int8_t, int8_t) {}
  void init(uint16_t, uint16_t) { setRotation(0); }
  void setSPISpeed(uint32_t) {}
  void setRotation(uint8_t r) {
    rotation = r;
    if (r & 1) { lw = 320; lh = 240; } else { lw = 240; lh = 320; }
    fb.assign((size_t)lw * lh, 0);
  }
  void invertDisplay(bool i) { inverted = i; }
  void fillScreen(uint16_t c) { fb.assign((size_t)lw * lh, c); }
  void startWrite() {}
  void endWrite() { present_count++; }
  void setAddrWindow(uint16_t x, uint16_t y, uint16_t w, uint16_t h) {
    wx = x; wy = y; ww = w; wh = h; cx = 0; cy = 0;
  }
  void writePixels(uint16_t *c, uint32_t len, bool = true, bool = false) {
    for (uint32_t i = 0; i < len; i++) {
      int px = wx + cx, py = wy + cy;
      if (px >= 0 && py >= 0 && px < lw && py < lh) fb[(size_t)py * lw + px] = c[i];
      if (++cx >= ww) { cx = 0; cy++; }
    }
  }
  uint8_t rotation = 0;
  bool inverted = false;
  int present_count = 0;
  int lw = 240, lh = 320;
  int wx = 0, wy = 0, ww = 0, wh = 0, cx = 0, cy = 0;
  std::vector<uint16_t> fb;
};
