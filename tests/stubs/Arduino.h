#pragma once
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#include <string>
#include <deque>
#include <vector>
#include <algorithm>

static const uint8_t D0 = 1;
static const uint8_t D1 = 2;
static const uint8_t D2 = 3;
static const uint8_t D8 = 7;
static const uint8_t D10 = 9;

unsigned long millis();

struct SerialStub {
  std::deque<uint8_t> rx;
  std::string tx;
  int available() { return (int)rx.size(); }
  int read() {
    if (rx.empty()) return -1;
    uint8_t b = rx.front();
    rx.pop_front();
    return b;
  }
  size_t read(uint8_t *dst, size_t n) {
    size_t i = 0;
    while (i < n && !rx.empty()) {
      dst[i++] = rx.front();
      rx.pop_front();
    }
    return i;
  }
  size_t readBytes(char *dst, size_t n) {
    size_t i = 0;
    while (i < n && !rx.empty()) {
      dst[i++] = (char)rx.front();
      rx.pop_front();
    }
    return i;
  }
  void print(const char *s) { tx += s; }
  void print(unsigned v) { tx += std::to_string(v); }
  void begin(unsigned long) {}
  size_t setRxBufferSize(size_t n) { return n; }
};

extern SerialStub Serial;
void setup();
void loop();
inline void delay(unsigned long) {}
