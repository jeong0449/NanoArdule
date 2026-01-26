#include <SPI.h>
#include <Usb.h>
#include <usbh_midi.h>
#include <SoftwareSerial.h>
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <string.h>

/*
  ===================== I2C LCD Wiring Tips (Arduino UNO) =====================

  - I2C pins on Arduino UNO:
      SDA = A4
      SCL = A5

  - Typical 20x4 I2C LCD backpack wiring:
      LCD VCC -> 5V
      LCD GND -> GND
      LCD SDA -> A4 (SDA)
      LCD SCL -> A5 (SCL)

  - Common I2C addresses:
      0x27 or 0x3F (depends on the backpack)

  Notes:
  - Keep I2C wires short and solid. Loose connections can cause random LCD glitches.
  - If the LCD becomes unstable at 400 kHz, comment out Wire.setClock(400000).
  - In this firmware, LCD updates are intentionally frozen while MIDI is active
    to avoid latency caused by I2C traffic.
*/

// ===================== Identity =====================
#define FW_NAME   "Ardule USB->DIN"
#define FW_VER    "v0.4 freezeLCD"

// ===================== LCD =====================
#define LCD_ADDR  0x27          // common: 0x27 or 0x3F
#define LCD_COLS  20
#define LCD_ROWS  4

#define LCD_UPDATE_MS      200  // update at 5Hz only when idle
#define LCD_IDLE_DELAY_MS  500  // resume LCD updates only after this quiet time since last MIDI

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

// ===================== USB Host =====================
USB Usb;
USBH_MIDI Midi(&Usb);

// ===================== Debug (optional) =====================
#define DEBUG 1
SoftwareSerial DBG(2, 3); // RX=D2(unused), TX=D3

#if DEBUG
  #define DPRINT(x)        DBG.print(x)
  #define DPRINTLN(x)      DBG.println(x)
  #define DPRINT_HEX(x)    DBG.print((x), HEX)
  #define DPRINTLN_HEX(x)  DBG.println((x), HEX)
#else
  #define DPRINT(x)        do{}while(0)
  #define DPRINTLN(x)      do{}while(0)
  #define DPRINT_HEX(x)    do{}while(0)
  #define DPRINTLN_HEX(x)  do{}while(0)
#endif

// ===================== DIN MIDI OUT =====================
#define MIDI_SERIAL Serial  // UNO HW Serial TX=D1
static inline void dinWrite1(uint8_t a) { MIDI_SERIAL.write(a); }
static inline void dinWrite2(uint8_t a, uint8_t b) { MIDI_SERIAL.write(a); MIDI_SERIAL.write(b); }
static inline void dinWrite3(uint8_t a, uint8_t b, uint8_t c) { MIDI_SERIAL.write(a); MIDI_SERIAL.write(b); MIDI_SERIAL.write(c); }

// --------------------- MIDI helpers ---------------------
static inline bool isStatus(uint8_t b) { return (b & 0x80) != 0; }

static inline uint8_t midiLenFromStatus(uint8_t st) {
  uint8_t hi = st & 0xF0;
  if (hi == 0xC0 || hi == 0xD0) return 2;  // PC, Channel Pressure
  if (hi >= 0x80 && hi <= 0xE0) return 3;  // Note/CC/PB/etc
  if (st >= 0xF8) return 1;                // Realtime
  if (st == 0xF1 || st == 0xF3) return 2;   // MTC QF, Song Select
  if (st == 0xF2) return 3;                // Song Position
  return 1;
}

// Parse A: p[0]=USB-MIDI header, p[1]=status, p[2]=d1, p[3]=d2
static inline bool bridgeA(const uint8_t p[4]) {
  uint8_t st = p[1];
  if (!isStatus(st)) return false;
  if (st == 0xF0) return false; // SysEx ignore now
  uint8_t len = midiLenFromStatus(st);
  if (len == 1) dinWrite1(st);
  else if (len == 2) dinWrite2(st, p[2] & 0x7F);
  else dinWrite3(st, p[2] & 0x7F, p[3] & 0x7F);
  return true;
}

// Parse B: p[0]=status, p[1]=d1, p[2]=d2
static inline bool bridgeB(const uint8_t p[4]) {
  uint8_t st = p[0];
  if (!isStatus(st)) return false;
  if (st == 0xF0) return false; // SysEx ignore now
  uint8_t len = midiLenFromStatus(st);
  if (len == 1) dinWrite1(st);
  else if (len == 2) dinWrite2(st, p[1] & 0x7F);
  else dinWrite3(st, p[1] & 0x7F, p[2] & 0x7F);
  return true;
}

// ===================== Runtime stats =====================
uint8_t lastUsbState = 0xFF;

uint32_t cntRecv = 0;
uint32_t cntDinA = 0;
uint32_t cntDinB = 0;
uint32_t cntSkip = 0;

// last packet (LCD RAW is OFF by default)
uint8_t lastP[4] = {0,0,0,0};
bool havePacket = false;

// Timestamp for freezing LCD while playing
static uint32_t lastMidiMs = 0;

// last event summary
struct MidiEventSummary {
  uint8_t status = 0;
  uint8_t d1 = 0;
  uint8_t d2 = 0;
  bool    valid = false;
  char    via[4] = "---";     // "A", "B", "AB", "SK"
  char    kind[8] = "----";   // "NOTEON", "CC", ...
} lastEvt;

static const char* kindFromStatus(uint8_t st) {
  uint8_t hi = st & 0xF0;
  if (hi == 0x80) return "NOTEOF";
  if (hi == 0x90) return "NOTEON";
  if (hi == 0xA0) return "POLYAT";
  if (hi == 0xB0) return "CC";
  if (hi == 0xC0) return "PC";
  if (hi == 0xD0) return "CHPR";
  if (hi == 0xE0) return "PITCH";
  if (st >= 0xF8) return "RT";
  if (st == 0xF0) return "SYSEX";
  if (st == 0xFE) return "ASENS";
  if (st == 0xF2) return "SPP";
  if (st == 0xF3) return "SS";
  if (st == 0xF1) return "MTC";
  return "SYS";
}

// ===================== LCD minimal traffic engine =====================
char lcdCache[LCD_ROWS][LCD_COLS + 1];

static void lcdWriteRowIfChanged(uint8_t row, const char* newRow) {
  if (row >= LCD_ROWS) return;

  char buf[LCD_COLS + 1];
  size_t n = strlen(newRow);
  if (n > LCD_COLS) n = LCD_COLS;
  memcpy(buf, newRow, n);
  for (size_t i = n; i < LCD_COLS; i++) buf[i] = ' ';
  buf[LCD_COLS] = '\0';

  if (strcmp(buf, lcdCache[row]) == 0) return;

  strcpy(lcdCache[row], buf);
  lcd.setCursor(0, row);
  lcd.print(buf);
}

static void lcdClearCache() {
  for (int r = 0; r < LCD_ROWS; r++) {
    lcdCache[r][0] = '\0';
  }
}

static void lcdWelcome() {
  lcd.clear();
  lcdClearCache();

  char r0[21], r1[21], r2[21], r3[21];
  snprintf(r0, sizeof(r0), "   %s", FW_NAME);
  snprintf(r1, sizeof(r1), "   %s", FW_VER);
  snprintf(r2, sizeof(r2), "  Initializing");
  snprintf(r3, sizeof(r3), "  Please wait");

  lcdWriteRowIfChanged(0, r0);
  lcdWriteRowIfChanged(1, r1);
  lcdWriteRowIfChanged(2, r2);
  lcdWriteRowIfChanged(3, r3);

  // dot animation (delay is OK only during boot)
  for (int i = 0; i < 10; i++) {
    lcd.setCursor(16, 2);
    int dots = (i % 3) + 1;
    lcd.print("   ");
    lcd.setCursor(16, 2);
    for (int d = 0; d < dots; d++) lcd.print('.');
    delay(280);
  }
  delay(250);
}

// LCD content composer
bool showRawOnLcd = false; // OFF by default

static void composeRow0(char* out) {
  snprintf(out, 21, "%s S=%u", FW_NAME, lastUsbState);
}

static void composeRow1(char* out) {
  if (!lastEvt.valid) {
    snprintf(out, 21, "Waiting MIDI...");
    return;
  }

  uint8_t st = lastEvt.status;
  uint8_t ch = (st & 0x0F) + 1;
  uint8_t hi = st & 0xF0;

  if (hi == 0x90 || hi == 0x80) {
    uint8_t note = lastEvt.d1 & 0x7F;
    uint8_t vel  = lastEvt.d2 & 0x7F;
    const char* k = (hi == 0x90 && vel > 0) ? "NOTEON" : "NOTEOF";
    snprintf(out, 21, "%s ch%u n%u v%u", k, ch, note, vel);
  } else if (hi == 0xB0) {
    uint8_t cc  = lastEvt.d1 & 0x7F;
    uint8_t val = lastEvt.d2 & 0x7F;
    snprintf(out, 21, "CC ch%u #%u=%u", ch, cc, val);
  } else if (hi == 0xC0) {
    uint8_t pc = lastEvt.d1 & 0x7F;
    snprintf(out, 21, "PC ch%u %u", ch, pc);
  } else if (st >= 0xF8) {
    snprintf(out, 21, "Realtime 0x%02X", st);
  } else {
    snprintf(out, 21, "%s st%02X d1%u d2%u", lastEvt.kind, st, lastEvt.d1 & 0x7F, lastEvt.d2 & 0x7F);
  }
}

static void composeRow2(char* out) {
  if (!lastEvt.valid) {
    snprintf(out, 21, "DIN via ----");
    return;
  }
  snprintf(out, 21, "DIN via %s  R%lu", lastEvt.via, (unsigned long)cntRecv);
}

static void composeRow3(char* out) {
  if (!showRawOnLcd) {
    snprintf(out, 21, "A%lu B%lu S%lu RAWoff",
      (unsigned long)cntDinA, (unsigned long)cntDinB, (unsigned long)cntSkip);
  } else {
    snprintf(out, 21, "%02X %02X %02X %02X",
      lastP[0], lastP[1], lastP[2], lastP[3]);
  }
}

// 5Hz refresh, called only when idle
static void lcdRefreshIfDue() {
  static uint32_t nextMs = 0;
  uint32_t now = millis();
  if ((int32_t)(now - nextMs) < 0) return;
  nextMs = now + LCD_UPDATE_MS;

  char r0[21], r1[21], r2[21], r3[21];
  composeRow0(r0);
  composeRow1(r1);
  composeRow2(r2);
  composeRow3(r3);

  lcdWriteRowIfChanged(0, r0);
  lcdWriteRowIfChanged(1, r1);
  lcdWriteRowIfChanged(2, r2);
  lcdWriteRowIfChanged(3, r3);
}

// ===================== setup / loop =====================
void setup() {
  pinMode(10, OUTPUT);
  digitalWrite(10, HIGH);

#if DEBUG
  DBG.begin(115200);
  delay(120);
  DPRINTLN(F("Ardule USB->DIN Bridge (freeze LCD while playing)"));
#endif

  MIDI_SERIAL.begin(31250);

  Wire.begin();
  // If 400 kHz is unstable, comment out the next line.
  Wire.setClock(400000);

  lcd.init();
  lcd.backlight();
  lcdClearCache();

  lcdWelcome();

  int rc = Usb.Init();
  if (rc == -1) {
#if DEBUG
    DPRINTLN(F("USB Host Shield init FAILED"));
#endif
    lcd.clear();
    lcdClearCache();
    lcdWriteRowIfChanged(0, "USB Host FAILED");
    lcdWriteRowIfChanged(1, "Check power/wiring");
    lcdWriteRowIfChanged(2, "LCD addr 0x27/3F");
    lcdWriteRowIfChanged(3, "Halt");
    while (1);
  }

#if DEBUG
  DPRINTLN(F("USB Host Shield init OK"));
#endif

  lastUsbState = Usb.getUsbTaskState();

  // LCD refresh runs only when idle. After boot, force the initial state so that
  // the welcome screen doesn't immediately get overwritten.
  lastMidiMs = millis(); // You could set this to 0 to allow immediate refresh, but we keep it as "now"
                         // to preserve the welcome screen right after boot.
}

void loop() {
  Usb.Task();

  // Update USB state (value only)
  uint8_t s = Usb.getUsbTaskState();
  if (s != lastUsbState) {
    lastUsbState = s;
#if DEBUG
    DPRINT(F("[USB] state=")); DPRINTLN(s);
#endif
  }

  // Receive MIDI packet
  uint8_t p[4] = {0,0,0,0};
  int r = Midi.RecvData(p);
  if (r > 0) {
    // ★ While playing: trigger LCD freeze
    lastMidiMs = millis();

    havePacket = true;
    memcpy(lastP, p, 4);
    cntRecv++;

#if DEBUG
    DPRINT(F("[RAW] "));
    DPRINT_HEX(p[0]); DPRINT(F(" "));
    DPRINT_HEX(p[1]); DPRINT(F(" "));
    DPRINT_HEX(p[2]); DPRINT(F(" "));
    DPRINTLN_HEX(p[3]);
#endif

    // Bridge (A/B auto)
    bool a = bridgeA(p);
    bool b = bridgeB(p);

    if (a && b) { strcpy(lastEvt.via, "AB"); cntDinA++; cntDinB++; }
    else if (a) { strcpy(lastEvt.via, "A");  cntDinA++; }
    else if (b) { strcpy(lastEvt.via, "B");  cntDinB++; }
    else        { strcpy(lastEvt.via, "SK"); cntSkip++; }

    // Event summary (for display) uses the successful parse
    uint8_t st = 0, d1 = 0, d2 = 0;
    if (a) { st = p[1]; d1 = p[2]; d2 = p[3]; }
    else if (b) { st = p[0]; d1 = p[1]; d2 = p[2]; }
    else { st = (p[1] ? p[1] : p[0]); d1 = p[2]; d2 = p[3]; }

    lastEvt.status = st;
    lastEvt.d1 = d1;
    lastEvt.d2 = d2;
    lastEvt.valid = true;

    const char* k = kindFromStatus(st);
    strncpy(lastEvt.kind, k, sizeof(lastEvt.kind)-1);
    lastEvt.kind[sizeof(lastEvt.kind)-1] = '\0';
  }

  // ===================== Key point: zero LCD updates while playing =====================
  // Refresh LCD (5Hz) only after MIDI has been quiet for at least 500 ms.
  uint32_t now = millis();
  if ((now - lastMidiMs) > LCD_IDLE_DELAY_MS) {
    lcdRefreshIfDue();
  }
}
