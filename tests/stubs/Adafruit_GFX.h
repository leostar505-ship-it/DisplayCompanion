#pragma once
#include <stdint.h>
#include <stdlib.h>
#include <vector>
#include <algorithm>

class GFXcanvas16 {
 public:
  GFXcanvas16(uint16_t w, uint16_t h) : W(w), H(h), buf((size_t)w * h, 0) {}
  uint16_t *getBuffer() { return buf.data(); }
  void fillScreen(uint16_t c) { std::fill(buf.begin(), buf.end(), c); }
  void drawPixel(int16_t x, int16_t y, uint16_t c) {
    if (x < 0 || y < 0 || x >= W || y >= H) return;
    buf[(size_t)y * W + x] = c;
  }
  void fillRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t c) {
    for (int16_t j = y; j < y + h; j++)
      for (int16_t i = x; i < x + w; i++) drawPixel(i, j, c);
  }
  void drawRect(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t c) {
    for (int16_t i = x; i < x + w; i++) {
      drawPixel(i, y, c);
      drawPixel(i, y + h - 1, c);
    }
    for (int16_t j = y; j < y + h; j++) {
      drawPixel(x, j, c);
      drawPixel(x + w - 1, j, c);
    }
  }
  void drawLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, uint16_t c) {
    int16_t steep = abs(y1 - y0) > abs(x1 - x0);
    if (steep) {
      std::swap(x0, y0);
      std::swap(x1, y1);
    }
    if (x0 > x1) {
      std::swap(x0, x1);
      std::swap(y0, y1);
    }
    int16_t dx = x1 - x0;
    int16_t dy = abs(y1 - y0);
    int16_t err = dx / 2;
    int16_t ystep = (y0 < y1) ? 1 : -1;
    for (; x0 <= x1; x0++) {
      if (steep) drawPixel(y0, x0, c);
      else drawPixel(x0, y0, c);
      err -= dy;
      if (err < 0) {
        y0 += ystep;
        err += dx;
      }
    }
  }
  void setTextSize(uint8_t) {}
  void setTextWrap(bool) {}
  void setTextColor(uint16_t) {}
  void setTextColor(uint16_t, uint16_t) {}
  void setCursor(int16_t, int16_t) {}
  void print(const char *) {}

 private:
  int16_t W, H;
  std::vector<uint16_t> buf;
};
