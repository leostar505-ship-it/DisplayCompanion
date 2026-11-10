# Display Companion

A Windows app that sends anything you want to the XIAO ESP32-S3 + 2.0" SPI screen (ST7789 240x320 by default, the 160x80 picture is shown at 2x; ST7735 160x80 via `PANEL_VARIANT`) over USB.

Modes (pick from the menu on the left):

| Mode | What it does |
|---|---|
| Visualiser | The audio visualiser project (v0.4.8) running as is, drawn at the screen size: radial spectrum + bass ring + waveform (default), radial spectrum + bass ring, waveform only, mirrored peak-hold bars. Colour: rainbow, loudness gradient (pink to red) or custom. Sensitivity, bar smoothness (evens out loud-quiet-loud-quiet and low frame rates), line smoothness, ring size, detection, normalise, kick/bass trigger, audio device picker. Bars also get a peak hold time (0 = the original behaviour). |
| Draw | Pen, eraser, line, rectangle, ellipse (outline or filled), flood fill, colour picker, brush size, undo/redo, save as PNG. Shapes preview while you drag. |
| Text | Any text, any font on your PC, any size or auto-fit, alignment, colours, sideways scrolling. |
| Image | Any picture or animated GIF, scaled to fit, fill or stretch, with brightness and contrast. |
| Terminal | Type a line, press Enter, it scrolls up on the board. |
| Raw | Send exact bytes (hex or text) or build protocol frames by hand. Shows the board's replies. |

The preview in the app is exactly what the board is sent. The "Simulator (no board)" entry in the Board list lets you try everything without hardware.

## 1. Wiring (screen to XIAO ESP32-S3)

| Wire | Screen pin | XIAO pin |
|---|---|---|
| Yellow | VCC | 3V3 |
| Black | GND | GND |
| Red | RST | D0 |
| Brown | DC | D1 |
| Blue | CS | D2 |
| Orange | SCL | D8 |
| Green | SDA | D10 |
| White | not used (7-pin screen has no backlight pin) | |

## 2. Flash the firmware

1. Install the Arduino IDE. In Boards Manager install **esp32 by Espressif Systems**.
2. In Library Manager install **Adafruit ST7735 and ST7789 Library** and **Adafruit GFX Library** (accept the dependencies).
3. Open `firmware/ScreenLink/ScreenLink.ino`.
4. Tools menu: Board = **XIAO_ESP32S3**, **USB CDC On Boot = Enabled**.
5. Upload. If the port does not show up, hold the BOOT button while plugging the USB in, then upload.
6. The screen should show "Display Companion / waiting for app" with a white border and four coloured corner squares (red top-left, green top-right, blue bottom-left, yellow bottom-right).

If the picture looks wrong, change the defines at the top of the sketch:

* Colours look inverted (negative): set `PANEL_VARIANT` to `1`, or tick "Invert colours" in the app.
* Red and blue are swapped: tick "Swap red/blue" in the app.
* Picture is upside down: tick "Flip 180" in the app, or swap `BASE_ROTATION` and `FLIPPED_ROTATION`.
* Picture is shifted or has a garbage stripe along one edge: this is the 160x80 panel offset. Tell me which edge and by how many pixels and I'll adjust it.
* Flickering or noise: lower `SPI_HZ` (try `20000000UL`).

## 3. Run the app

Python 3.10 or newer on Windows:

```
py -m pip install -r requirements.txt
py run_screenlink.py
```

Or double-click `run.bat`. Pick your board in the Board list (it shows the ESP32-S3 COM port) and press Connect, then Test link. The status bar should say the board answered `SCREENLINK 1 160x80`.

The Visualiser uses WASAPI loopback (whatever is playing through your speakers). If that is unavailable it falls back to a built-in demo signal and says so under the Response sliders.

To build a standalone exe: run `build_exe.bat`, the result is in `dist\DisplayCompanion\DisplayCompanion.exe`.

To build a proper Windows installer (installs to Program Files, adds a desktop shortcut and Start menu entry, has an uninstaller): run `build_installer.bat`. It builds the exe, installs Inno Setup with winget if needed, and writes `installer_output\DisplayCompanion-Setup.exe`.

## Claude tab (voice assistant)

Pick **Claude** in the mode list, then open **Setup** and choose how to talk to Claude. **My Claude Code login** (default) runs `claude -p` in the background, so it uses your Claude plan and needs Claude Code installed and signed in. **API key** uses Anthropic API credits instead (the key is stored only in `%APPDATA%\DisplayCompanion\assistant.json`).

- **Hey Claude**: click *Download voice model* once (about 40 MB, runs offline afterwards). While the Claude tab is open the microphone listens for "Hey Claude", then records your question until you stop talking.
- **Hotkey**: default `ctrl+alt+c`, works in any app. Change it in Setup.
- **Ask without talking**: type in the Ask box.
- Each question can include a screenshot of your screen (untick it to turn that off). The HUD hides itself before the screenshot, and the question is sent with "Sent via Display Companion" appended.
- The reply is trimmed to what fits on the screen at the chosen font size and typed out like real typing. The font and size are on the Ask Claude tab, with a live count of how many characters fit.
- The orange HUD card (listening, screenshot, thinking, responding, done, error) and its sound cues can be turned off or resized. It cannot show over exclusive-fullscreen games.

## Protocol (for the Raw tab or your own tools)

Every message from the PC is a frame:

```
A5 5A | cmd | len (2 bytes, little endian) | payload | checksum
```

The checksum is `(cmd + len_low + len_high + sum of payload bytes) & 0xFF`. Colours are RGB565, little endian. Coordinates are single bytes (screen is 160x80).

| Cmd | Name | Payload |
|---|---|---|
| 01 | HELLO | none. Board replies with a line `SCREENLINK 1 160x80` |
| 02 | CLEAR | colour (2) |
| 03 | RECTS | count (1), then count of: x, y, w, h (1 each), colour (2) |
| 04 | LINES | count (1), then count of: x0, y0, x1, y1 (1 each), colour (2) |
| 05 | PIXELS | count (2), then count of: x, y (1 each), colour (2) |
| 06 | IMAGE | x, y, w, h (1 each), then w*h RGB565 pixels |
| 07 | TEXT | x, y, size (1 each), fg (2), bg (2), flags (1, bit 0 = opaque background), length (1), ASCII text |
| 08 | FLIP | 0 or 1 |
| 09 | INVERT | 0 or 1 |
| 0A | SWAP_RB | 0 or 1 |
| 0C | PRESENT | none. Pushes the drawing to the screen now |

Drawing commands go to an off-screen buffer. The board shows it on PRESENT, or about 3 ms after the data stops arriving. Frames with a bad checksum are dropped and the board answers `ERR chk`.

## Tests

```
py -m pip install pytest
py -m pytest tests
```

The firmware tests compile `ScreenLink.ino` with stand-in Arduino libraries (needs g++) and check that the board's drawing matches the app's preview pixel for pixel.

## One-file installer from GitHub

Push this folder to a GitHub repo, then create a tag such as `v1.0` (or run the "Build installer" workflow by hand under Actions). GitHub builds on Windows and attaches `DisplayCompanion-Setup.exe` to the release (or to the run as an artifact). That single exe installs to Program Files and adds the desktop shortcut.
