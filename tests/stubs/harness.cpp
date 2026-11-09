#include <stdio.h>
#include <stdlib.h>
#include <vector>
#include "Arduino.h"
#include "Adafruit_ST7735.h"

static unsigned long g_ms = 0;
unsigned long millis() { return g_ms; }
SerialStub Serial;
SPIClass SPI;

extern Adafruit_ST7735 tft;

int main(int argc, char **argv) {
  if (argc < 4) return 2;
  size_t chunk = (size_t)atoi(argv[3]);
  FILE *in = fopen(argv[1], "rb");
  if (!in) return 3;
  std::vector<uint8_t> data;
  uint8_t tmp[4096];
  size_t n;
  while ((n = fread(tmp, 1, sizeof tmp, in)) > 0) data.insert(data.end(), tmp, tmp + n);
  fclose(in);

  setup();
  for (size_t i = 0; i < data.size(); i += chunk) {
    size_t end = i + chunk < data.size() ? i + chunk : data.size();
    for (size_t j = i; j < end; j++) Serial.rx.push_back(data[j]);
    loop();
    g_ms += 1;
  }
  if (argc > 4) g_ms += (unsigned long)atol(argv[4]);
  for (int k = 0; k < 20; k++) {
    g_ms += 5;
    loop();
  }

  FILE *out = fopen(argv[2], "wb");
  if (!out) return 4;
  fwrite(tft.last.data(), 2, tft.last.size(), out);
  fclose(out);
  fwrite(Serial.tx.data(), 1, Serial.tx.size(), stdout);
  fprintf(stderr, "presents=%d rotation=%d inverted=%d\n", tft.present_count, tft.rotation, (int)tft.inverted);
  return 0;
}
