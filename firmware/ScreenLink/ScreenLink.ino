// Display Companion firmware 1.5.1
#include <Arduino.h>
#include <SPI.h>
#include <Adafruit_GFX.h>

//  PANEL_VARIANT: 0 = ST7735 160x80, 1 = ST7735 160x80 (plugin), 2 = ST7789 240x320 (shown 2x)
#ifndef PANEL_VARIANT
#define PANEL_VARIANT 2
#endif
#if PANEL_VARIANT == 2
#define BASE_ROTATION 3
#define FLIPPED_ROTATION 1
#else
#define BASE_ROTATION 1
#define FLIPPED_ROTATION 3
#endif
#define FW_VERSION "1.5.1"
#define SPI_HZ 40000000UL

#if PANEL_VARIANT == 2
#include <Adafruit_ST7789.h>
#else
#include <Adafruit_ST7735.h>
#endif

#define PIN_CS D2
#define PIN_DC D1
#define PIN_RST D0
#define PIN_SCK D8
#define PIN_MOSI D10

static const int W = 160;
#ifndef SCREEN_H
#if PANEL_VARIANT == 2
#define SCREEN_H 120
#else
#define SCREEN_H 80
#endif
#endif
static const int H = SCREEN_H;
static const size_t MAX_PAYLOAD = 40000;
static const unsigned long IDLE_PRESENT_MS = 8;
static const unsigned long FRAME_TIMEOUT_MS = 300;

static const uint8_t MAGIC1 = 0xA5;
static const uint8_t MAGIC2 = 0x5A;

static const uint8_t CMD_HELLO = 0x01;
static const uint8_t CMD_CLEAR = 0x02;
static const uint8_t CMD_RECTS = 0x03;
static const uint8_t CMD_LINES = 0x04;
static const uint8_t CMD_PIXELS = 0x05;
static const uint8_t CMD_IMAGE = 0x06;
static const uint8_t CMD_TEXT = 0x07;
static const uint8_t CMD_FLIP = 0x08;
static const uint8_t CMD_INVERT = 0x09;
static const uint8_t CMD_SWAP_RB = 0x0A;
static const uint8_t CMD_PRESENT = 0x0C;
static const uint8_t CMD_HEARTBEAT = 0x0D;
static const unsigned long APP_TIMEOUT_MS = 3000;

#if PANEL_VARIANT == 2
Adafruit_ST7789 tft(&SPI, PIN_CS, PIN_DC, PIN_RST);
static uint16_t rowbuf[W * 4];
#else
Adafruit_ST7735 tft(&SPI, PIN_CS, PIN_DC, PIN_RST);
#endif
GFXcanvas16 canvas(W, H);

alignas(4) static uint8_t payload[MAX_PAYLOAD];
#if PANEL_VARIANT != 2
static uint16_t swapped[W * H];
#endif

// Two-frame pipeline. The parser draws into `canvas`; on PRESENT the canvas is copied into a
// frame slot and a second core (or, in the test harness, loop()) pushes the slot to the screen
// while the next frame is already being received. At most one frame is being drawn and one is
// waiting; a newer frame replaces a waiting one (its ack is still returned).
struct Frame {
  uint16_t buf[W * H];
  uint8_t quarter;
  bool swap;
  bool ack;
  int16_t x0, y0, x1, y1;
};
static Frame frames[2];
static volatile int drawingIdx = -1;
static volatile int pendingIdx = -1;
static volatile int ackOwed = 0;

#ifdef ARDUINO_ARCH_ESP32
static SemaphoreHandle_t qLock = NULL;    // protects the slot bookkeeping
static SemaphoreHandle_t tftLock = NULL;  // protects the screen / SPI
#define Q_TAKE() xSemaphoreTake(qLock, portMAX_DELAY)
#define Q_GIVE() xSemaphoreGive(qLock)
#define TFT_TAKE() xSemaphoreTake(tftLock, portMAX_DELAY)
#define TFT_GIVE() xSemaphoreGive(tftLock)
#else
#define Q_TAKE()
#define Q_GIVE()
#define TFT_TAKE()
#define TFT_GIVE()
#endif

enum State : uint8_t { S_SYNC1, S_SYNC2, S_CMD, S_LEN0, S_LEN1, S_PAYLOAD, S_CHK };

static State state = S_SYNC1;
static uint8_t curCmd = 0;
static uint16_t curLen = 0;
static uint16_t gotLen = 0;
static uint8_t runSum = 0;
static unsigned long lastByteMs = 0;
static unsigned long lastPresentMs = 0;
static unsigned long lastErrMs = 0;
static unsigned long lastAppMs = 0;
static bool appActive = false;
static bool dirty = false;
static bool swapRB = false;
static uint8_t quarter = 0;
static int16_t dx0 = W, dy0 = H, dx1 = 0, dy1 = 0;

static void markDirty(int x, int y, int w, int h) {
  int x1 = x + w, y1 = y + h;
  if (x < 0) x = 0;
  if (y < 0) y = 0;
  if (x1 > W) x1 = W;
  if (y1 > H) y1 = H;
  if (x1 <= x || y1 <= y) return;
  if (x < dx0) dx0 = x;
  if (y < dy0) dy0 = y;
  if (x1 > dx1) dx1 = x1;
  if (y1 > dy1) dy1 = y1;
}
static void markAll() { markDirty(0, 0, W, H); }

static inline uint16_t rd16(const uint8_t *p) {
  return (uint16_t)p[0] | ((uint16_t)p[1] << 8);
}

static void applyRotation(uint8_t q);

static void drawFrame(const Frame &f) {
  const uint16_t *src = f.buf;
  const bool sw = f.swap;
  const uint8_t qt = f.quarter;
#if PANEL_VARIANT == 2
  if (f.x1 <= f.x0 || f.y1 <= f.y0) return;
  tft.startWrite();
  if (qt & 1) {
    int i0, i1, j0, j1;
    if (qt == 1) {
      i0 = H - f.y1; i1 = H - f.y0; j0 = f.x0; j1 = f.x1;
    } else {
      i0 = f.y0; i1 = f.y1; j0 = W - f.x1; j1 = W - f.x0;
    }
    const int n = (i1 - i0) * 2;
    tft.setAddrWindow((240 - H * 2) / 2 + i0 * 2, j0 * 2, n, (j1 - j0) * 2);
    for (int j = j0; j < j1; j++) {
      for (int i = i0; i < i1; i++) {
        int y = (qt == 1) ? (H - 1 - i) : i;
        int x = (qt == 1) ? j : (W - 1 - j);
        uint16_t v = src[y * W + x];
        if (sw) v = (uint16_t)(((v & 0x1F) << 11) | (v & 0x07E0) | (v >> 11));
        rowbuf[2 * (i - i0)] = v;
        rowbuf[2 * (i - i0) + 1] = v;
      }
      memcpy(rowbuf + n, rowbuf, n * 2);
      tft.writePixels(rowbuf, n * 2);
    }
    tft.endWrite();
    return;
  }
  const int n = (f.x1 - f.x0) * 2;
  tft.setAddrWindow(f.x0 * 2, (240 - H * 2) / 2 + f.y0 * 2, n, (f.y1 - f.y0) * 2);
  for (int y = f.y0; y < f.y1; y++) {
    const uint16_t *row = src + y * W;
    for (int x = f.x0; x < f.x1; x++) {
      uint16_t v = row[x];
      if (sw) v = (uint16_t)(((v & 0x1F) << 11) | (v & 0x07E0) | (v >> 11));
      rowbuf[2 * (x - f.x0)] = v;
      rowbuf[2 * (x - f.x0) + 1] = v;
    }
    memcpy(rowbuf + n, rowbuf, n * 2);
    tft.writePixels(rowbuf, n * 2);
  }
  tft.endWrite();
#else
  if (sw) {
    for (int i = 0; i < W * H; i++) {
      uint16_t v = src[i];
      swapped[i] = (uint16_t)(((v & 0x1F) << 11) | (v & 0x07E0) | (v >> 11));
    }
    tft.drawRGBBitmap(0, 0, swapped, W, H);
  } else {
    tft.drawRGBBitmap(0, 0, (uint16_t *)src, W, H);
  }
#endif
}

// Copy the canvas into a slot for the draw side. If a frame is already waiting it is replaced.
static void enqueueFrame(bool ack) {
  Q_TAKE();
  int idx;
  int16_t bx0 = dx0, by0 = dy0, bx1 = dx1, by1 = dy1;
  if (pendingIdx >= 0) {
    idx = pendingIdx;
    if (frames[idx].ack) ackOwed = ackOwed + 1;
    if (frames[idx].x1 > frames[idx].x0 && frames[idx].y1 > frames[idx].y0) {
      if (bx1 <= bx0 || by1 <= by0) {
        bx0 = frames[idx].x0; by0 = frames[idx].y0; bx1 = frames[idx].x1; by1 = frames[idx].y1;
      } else {
        if (frames[idx].x0 < bx0) bx0 = frames[idx].x0;
        if (frames[idx].y0 < by0) by0 = frames[idx].y0;
        if (frames[idx].x1 > bx1) bx1 = frames[idx].x1;
        if (frames[idx].y1 > by1) by1 = frames[idx].y1;
      }
    }
  } else {
    idx = (drawingIdx == 0) ? 1 : 0;
  }
  memcpy(frames[idx].buf, canvas.getBuffer(), sizeof(frames[idx].buf));
  frames[idx].quarter = quarter;
  frames[idx].swap = swapRB;
  frames[idx].ack = ack;
  frames[idx].x0 = bx0; frames[idx].y0 = by0; frames[idx].x1 = bx1; frames[idx].y1 = by1;
  dx0 = W; dy0 = H; dx1 = 0; dy1 = 0;
  pendingIdx = idx;
  dirty = false;
  lastPresentMs = millis();
  Q_GIVE();
}

// Draw the waiting frame, if any. Returns true when something was drawn.
static bool serviceDraw() {
  Q_TAKE();
  if (pendingIdx < 0) {
    Q_GIVE();
    return false;
  }
  int idx = pendingIdx;
  drawingIdx = idx;
  pendingIdx = -1;
  Q_GIVE();
  TFT_TAKE();
  drawFrame(frames[idx]);
  TFT_GIVE();
  Q_TAKE();
  if (frames[idx].ack) ackOwed = ackOwed + 1;
  drawingIdx = -1;
  Q_GIVE();
  return true;
}

static void sendAcks() {
  while (true) {
    Q_TAKE();
    int n = ackOwed;
    if (n > 0) ackOwed = n - 1;
    Q_GIVE();
    if (n <= 0) break;
    Serial.print("K\n");
  }
}

#ifdef ARDUINO_ARCH_ESP32
static void drawTask(void *) {
  for (;;) {
    if (!serviceDraw()) vTaskDelay(1);
  }
}
#endif

static void reportError(const char *msg) {
  static bool haveErr = false;
  unsigned long now = millis();
  if (haveErr && now - lastErrMs < 200) return;
  haveErr = true;
  lastErrMs = now;
  Serial.print("ERR ");
  Serial.print(msg);
  Serial.print("\n");
}

static void doClear(const uint8_t *p, uint16_t n) {
  if (n < 2) return;
  canvas.fillScreen(rd16(p));
  markAll();
  dirty = true;
}

static void doRects(const uint8_t *p, uint16_t n) {
  if (n < 1) return;
  uint8_t count = p[0];
  if ((uint32_t)1 + (uint32_t)count * 6 > n) return;
  for (uint8_t i = 0; i < count; i++) {
    const uint8_t *r = p + 1 + i * 6;
    canvas.fillRect(r[0], r[1], r[2], r[3], rd16(r + 4));
    markDirty(r[0], r[1], r[2], r[3]);
  }
  dirty = true;
}

static void doLines(const uint8_t *p, uint16_t n) {
  if (n < 1) return;
  uint8_t count = p[0];
  if ((uint32_t)1 + (uint32_t)count * 6 > n) return;
  for (uint8_t i = 0; i < count; i++) {
    const uint8_t *r = p + 1 + i * 6;
    canvas.drawLine(r[0], r[1], r[2], r[3], rd16(r + 4));
    int lx = r[0] < r[2] ? r[0] : r[2], ly = r[1] < r[3] ? r[1] : r[3];
    int lw = (r[0] < r[2] ? r[2] - r[0] : r[0] - r[2]) + 1, lh = (r[1] < r[3] ? r[3] - r[1] : r[1] - r[3]) + 1;
    markDirty(lx, ly, lw, lh);
  }
  dirty = true;
}

static void doPixels(const uint8_t *p, uint16_t n) {
  if (n < 2) return;
  uint16_t count = rd16(p);
  if ((uint32_t)2 + (uint32_t)count * 4 > n) return;
  for (uint16_t i = 0; i < count; i++) {
    const uint8_t *r = p + 2 + i * 4;
    canvas.drawPixel(r[0], r[1], rd16(r + 2));
    markDirty(r[0], r[1], 1, 1);
  }
  dirty = true;
}

static void doImage(const uint8_t *p, uint16_t n) {
  if (n < 4) return;
  int x = p[0], y = p[1], w = p[2], h = p[3];
  if ((uint32_t)n != (uint32_t)4 + (uint32_t)w * h * 2) return;
  uint16_t *buf = canvas.getBuffer();
  const uint8_t *src = p + 4;
  for (int row = 0; row < h; row++) {
    int py = y + row;
    for (int col = 0; col < w; col++) {
      int px = x + col;
      if (px < W && py < H) buf[py * W + px] = rd16(src);
      src += 2;
    }
  }
  markDirty(x, y, w, h);
  dirty = true;
}

static void doText(const uint8_t *p, uint16_t n) {
  if (n < 9) return;
  int x = p[0], y = p[1], size = p[2];
  uint16_t fg = rd16(p + 3);
  uint16_t bg = rd16(p + 5);
  uint8_t flags = p[7];
  uint8_t len = p[8];
  if ((uint32_t)9 + len > n) return;
  char tmp[256];
  memcpy(tmp, p + 9, len);
  tmp[len] = 0;
  if (size < 1) size = 1;
  canvas.setTextSize(size);
  canvas.setTextWrap(false);
  if (flags & 1) canvas.setTextColor(fg, bg);
  else canvas.setTextColor(fg);
  canvas.setCursor(x, y);
  canvas.print(tmp);
  markDirty(x, y, len * 6 * size, 8 * size);
  dirty = true;
}

static void execute(uint8_t cmd, const uint8_t *p, uint16_t n) {
  switch (cmd) {
    case CMD_HELLO:
      Serial.print("SCREENLINK 1 160x120 fw " FW_VERSION "\n");
      break;
    case CMD_CLEAR:
      doClear(p, n);
      break;
    case CMD_RECTS:
      doRects(p, n);
      break;
    case CMD_LINES:
      doLines(p, n);
      break;
    case CMD_PIXELS:
      doPixels(p, n);
      break;
    case CMD_IMAGE:
      doImage(p, n);
      break;
    case CMD_TEXT:
      doText(p, n);
      break;
    case CMD_FLIP:
      if (n >= 1) applyRotation(p[0] & 3);
      markAll();
      dirty = true;
      break;
    case CMD_INVERT:
      TFT_TAKE();
#if PANEL_VARIANT == 2
      if (n >= 1) tft.invertDisplay(p[0] == 0);
#else
      if (n >= 1) tft.invertDisplay(p[0] != 0);
#endif
      TFT_GIVE();
      break;
    case CMD_SWAP_RB:
      if (n >= 1) swapRB = p[0] != 0;
      markAll();
      dirty = true;
      break;
    case CMD_PRESENT:
      enqueueFrame(true);
      break;
    case CMD_HEARTBEAT:
      break;
    default:
      break;
  }
}

static void consume() {
  while (Serial.available() > 0) {
    lastByteMs = millis();
    if (state == S_PAYLOAD) {
      size_t need = (size_t)curLen - gotLen;
      size_t take = (size_t)Serial.available();
      if (take > need) take = need;
      size_t r = Serial.read(payload + gotLen, take);
      for (size_t i = 0; i < r; i++) runSum = (uint8_t)(runSum + payload[gotLen + i]);
      gotLen = (uint16_t)(gotLen + r);
      if (gotLen == curLen) state = S_CHK;
      continue;
    }
    uint8_t b = (uint8_t)Serial.read();
    switch (state) {
      case S_SYNC1:
        if (b == MAGIC1) state = S_SYNC2;
        break;
      case S_SYNC2:
        if (b == MAGIC2) state = S_CMD;
        else if (b != MAGIC1) state = S_SYNC1;
        break;
      case S_CMD:
        curCmd = b;
        runSum = b;
        state = S_LEN0;
        break;
      case S_LEN0:
        curLen = b;
        runSum = (uint8_t)(runSum + b);
        state = S_LEN1;
        break;
      case S_LEN1:
        curLen = (uint16_t)(curLen | ((uint16_t)b << 8));
        runSum = (uint8_t)(runSum + b);
        if (curLen > MAX_PAYLOAD) {
          state = S_SYNC1;
        } else {
          gotLen = 0;
          state = curLen ? S_PAYLOAD : S_CHK;
        }
        break;
      case S_CHK:
        if (b == runSum) {
          appActive = true;
          lastAppMs = millis();
          execute(curCmd, payload, curLen);
        }
        else reportError("chk");
        state = S_SYNC1;
        break;
      default:
        state = S_SYNC1;
        break;
    }
  }
}

static void applyRotation(uint8_t q) {
  TFT_TAKE();
#if PANEL_VARIANT == 2
  quarter = q;
  tft.setRotation((q & 1) ? 0 : (q == 2 ? FLIPPED_ROTATION : BASE_ROTATION));
  tft.fillScreen(0);
#else
  quarter = (q == 2) ? 2 : 0;
  tft.setRotation(quarter == 2 ? FLIPPED_ROTATION : BASE_ROTATION);
#endif
  TFT_GIVE();
}

static void splash() {
  canvas.fillScreen(0x0000);
  canvas.drawRect(0, 0, W, H, 0xFFFF);
  canvas.fillRect(1, 1, 8, 8, 0xF800);
  canvas.fillRect(W - 9, 1, 8, 8, 0x07E0);
  canvas.fillRect(1, H - 9, 8, 8, 0x001F);
  canvas.fillRect(W - 9, H - 9, 8, 8, 0xFFE0);
  canvas.setTextWrap(false);
  canvas.setTextSize(1);
  canvas.setTextColor(0xFFFF);
  canvas.setCursor(29, H / 2 - 12);
  canvas.print("Display Companion");
  canvas.setTextSize(1);
  canvas.setTextColor(0x07FF);
  canvas.setCursor(36, H / 2 + 8);
  canvas.print("waiting for app");
  canvas.setTextColor(0x8410);
  canvas.setCursor(56, H / 2 + 24);
  canvas.print("fw " FW_VERSION);
  markAll();
  enqueueFrame(false);
  serviceDraw();
}

void setup() {
#ifdef ARDUINO_ARCH_ESP32
  qLock = xSemaphoreCreateMutex();
  tftLock = xSemaphoreCreateMutex();
#endif
  Serial.setRxBufferSize(32768);
  Serial.begin(115200);
  SPI.begin(PIN_SCK, -1, PIN_MOSI, PIN_CS);
#if PANEL_VARIANT == 2
  tft.init(240, 320);
  tft.invertDisplay(true);
  tft.fillScreen(0);
#elif PANEL_VARIANT == 1
  tft.initR(INITR_MINI160x80_PLUGIN);
#else
  tft.initR(INITR_MINI160x80);
#endif
  tft.setSPISpeed(SPI_HZ);
  tft.setRotation(BASE_ROTATION);
  tft.fillScreen(0);
  splash();
#ifdef ARDUINO_ARCH_ESP32
  xTaskCreatePinnedToCore(drawTask, "draw", 4096, NULL, 2, NULL, 0);
#endif
}

void loop() {
  consume();
  if (state != S_SYNC1 && millis() - lastByteMs > FRAME_TIMEOUT_MS) state = S_SYNC1;
  if (appActive && millis() - lastAppMs > APP_TIMEOUT_MS && millis() - lastByteMs > APP_TIMEOUT_MS) {
    appActive = false;
    splash();
  }
  if (dirty) {
    unsigned long now = millis();
    if (state == S_SYNC1 && (now - lastByteMs >= IDLE_PRESENT_MS || now - lastPresentMs >= 60)) enqueueFrame(false);
  }
#ifndef ARDUINO_ARCH_ESP32
  serviceDraw();
#endif
  sendAcks();
}
