/*
  111925_NanoEvery_ArdulePlayer_v2.5_modernNames.ino
  Board : Arduino Nano Every (ATmega4809)

  Ardule Drum Pattern Player v2.5
  - 2-bar absolute-time loop engine (SSE v2.x core)
  - ADP v2.2 (binary) 2-bar drum patterns from SD
  - SONG play mode (Type 0 MIDI)
  - Preview All (no preload, single pattern buffer)
*/

#include <string.h>
#include <SPI.h>
#include <SD.h>
#include <Wire.h>
#include <hd44780.h>
#include <EEPROM.h>
#include "GMDrumNames.h"
#include <hd44780ioClass/hd44780_I2Cexp.h>

// Built-in (emergency) pattern payload/index (stored in flash)
// NOTE: EMERGENCY_PATTERN_COUNT is defined in emergency_payload.h
#include "emergency_index.h"
#include "emergency_payload.h"

// Engine helpers are implemented in other .ino units; forward-declare to
// avoid Arduino concatenation ordering issues.
void stopAllPlaybackAndReset(bool toIdle);

// SONG UI preview: read BPM from selected .MID/.ADS
bool readSongBpmFromPath(const char *path, bool isAds, uint16_t &bpmOut);

struct LongPressState;

//////////////////// Pins ////////////////////
#define LCD_COLS      16
#define LCD_ROWS      2

#define ENC_A_PIN     2
#define ENC_B_PIN     3
#define ENC_BTN_PIN   4

#define BTN_PLAY      A3   // PLAY/PAUSE
#define BTN_INTERNAL  5    // D5 long -> INTERNAL (지금은 클릭 진입 테스트)
#define BTN_STOP      6    // D6 STOP/BACK
#define BTN_BPM_DN    8    // D8 (swapped)
#define BTN_BPM_UP    7    // D7 (swapped)
#define BTN_METRO     A6   // A6 long-press -> METRONOME

#define LED_TX        9    // D9 (TX indicator)
#define LED_A0        A0   // Beat/버튼 피드백
#define LED_A1        A1   // Beat
#define LED_A2        A2   // Beat

#define SD_CS_PIN     10   // SD 카드 CS

// MIDI 출력: Nano Every에서는 Serial1 이 하드웨어 UART (D0/D1)
#define MIDI_SERIAL Serial1

uint32_t txLedOffAtMs = 0;

//////////////////// LCD ////////////////////
hd44780_I2Cexp lcd;

// 5x8 custom char for "∞" 비슷한 모양
byte charInf[8] = {
  B00000,
  B00000,
  B01010,  //  .#.#.
  B10101,  //  #.#.#
  B10101,  //  #.#.#
  B01010,  //  .#.#.
  B00000,
  B00000
};

// 5x8 custom char for "▶" (play 아이콘)
byte charPlay[8] = {
  B00000,
  B01000,  //  .#...
  B01100,  //  .##..
  B01110,  //  .###.
  B01100,  //  .##..
  B01000,  //  .#...
  B00000,
  B00000
};

byte charUp[8] = {
  B00100,
  B01110,
  B11111,
  B00100,
  B00100,
  B00100,
  B00100,
  B00000
};

byte charDown[8] = {
  B00100,
  B00100,
  B00100,
  B00100,
  B00100,
  B11111,
  B01110,
  B00100
};


#define CHAR_INF   0
#define CHAR_PLAY  1


#define CHAR_UP    2
#define CHAR_DOWN  3

//////////////////// State Machine ////////////////////
enum UiMode : uint8_t {
  UIMODE_MAIN = 0,
  UIMODE_PAT_GEN,
  UIMODE_PAT_LIST,
  UIMODE_PAT_SINGLE,
  UIMODE_SONGS_ROOT,
  UIMODE_SONGS_FILELIST,
  UIMODE_SONG_PLAY,
  UIMODE_INTERNAL,
  UIMODE_METRO,
  UIMODE_SETTINGS,
  UIMODE_PARAM_MENU
};

UiMode uiMode = UIMODE_MAIN;
UiMode prevTopMode = UIMODE_MAIN;

enum SettingsUiMode : uint8_t {
  SETTINGS_UI_MENU = 0,
  SETTINGS_UI_EDIT_MODULE,
  SETTINGS_UI_EDIT_METRO_SOUND
};

SettingsUiMode settingsUiMode = SETTINGS_UI_MENU;

// --- 재생 상태 ---
enum PlayState : uint8_t {
  PLAYSTATE_IDLE = 0,
  PLAYSTATE_PLAYING,
  PLAYSTATE_PAUSED
};

PlayState playState = PLAYSTATE_IDLE;

// 재생 소스 종류
enum PlaySource : uint8_t {
  PLAY_SRC_NONE = 0,
  PLAY_SRC_PATTERN,
  PLAY_SRC_SONG
};

PlaySource playSource = PLAY_SRC_NONE;

// 현재 재생 중인 파일 경로
char currentFilePath[32];
bool playFileOpen = false;
File playFile;

// MIDI 타이밍
uint16_t midiPPQ        = 480;
uint32_t usPerQuarter   = 500000;   // 120 BPM
uint32_t usPerTick      = 1041;
uint32_t nextEventUs    = 0;
uint32_t songPauseStartUs = 0;
bool     haveNextEvent  = false;
bool     endOfTrack     = false;
uint8_t  runningStatus  = 0;

// 패턴 절대시간(틱 기반) 재생 버퍼
const uint16_t PAT_MAX_EVENTS = 128;

struct PatternEvent {
  uint16_t tick;   // 루프 시작으로부터의 절대 tick
  uint8_t  status;
  uint8_t  d1;
  uint8_t  d2;
};

// Pattern Engine state
struct PatternEngineState {
  PatternEvent events[PAT_MAX_EVENTS];
  uint16_t     eventCount;
  uint16_t     eventIndex;
  uint16_t     loopLenTicks;
  uint32_t     loopStartUs;
  bool         loaded;
};

// 단일 패턴 버퍼 (active only)
PatternEngineState patA;
PatternEngineState* patCur = &patA;

// 접근 매크로
#define patEvents       (patCur->events)
#define patEventCount   (patCur->eventCount)
#define patEventIndex   (patCur->eventIndex)
#define patLoopLenTicks (patCur->loopLenTicks)
#define patLoopStartUs  (patCur->loopStartUs)
#define patLoaded       (patCur->loaded)

// 2마디 기준 비트 엔진 (4/4 → 8박)
const uint8_t BEATS_PER_BAR   = 4;
const uint8_t BARS_PER_LOOP   = 2;
const uint8_t TOTAL_BEATS     = BEATS_PER_BAR * BARS_PER_LOOP; // 8

uint8_t   beatIndex        = 0;
uint32_t  nextBeatMs       = 0;
uint32_t  beatIntervalMs   = 500;

int8_t    beatLedPin       = -1;
uint32_t  beatLedOffAtMs   = 0;
uint32_t  metroAccentOffAtMs = 0;

// 패턴(Preview / Single) 일시정지용
uint32_t patternPauseStartUs = 0;


// 메인 메뉴
enum MainMenuItem : uint8_t {
  MM_PATTERNS = 0,
  MM_SONGS,
  MM_METRONOME,
  MM_INTERNAL,
  MM_SETTINGS,
  MM_COUNT
};
int16_t mainCursor = 0;

// PATTERNS/INDEX.TXT 관련
const uint8_t MAX_PATTERNS = 80;
const uint8_t MAX_GENRES   = 16;
const uint8_t GEN_LEN      = 4;
const uint8_t FILEBASE_LEN = 9;

struct PatternInfo {
  char gen[GEN_LEN];
  char fileBase[FILEBASE_LEN];
};

PatternInfo patterns[MAX_PATTERNS];
uint8_t patternCount = 0;

struct GenreInfo {
  char gen[GEN_LEN];
  uint8_t count;
};

GenreInfo genres[MAX_GENRES];
uint8_t genreCount = 0;



enum GenreSortMode : uint8_t {
  SORT_COUNT_DESC = 0,  // N↓
  SORT_COUNT_ASC  = 1,  // N↑
  SORT_ALPHA_ASC  = 2,  // A→Z
  SORT_ALPHA_DESC = 3   // Z→A
};

// Display indirection: display index -> genres[] index
uint8_t genreOrder[MAX_GENRES];
GenreSortMode genreSortMode = SORT_COUNT_DESC;

// A6 short-press uses release-click detection (to avoid firing on long-press)
uint32_t metroDownMs = 0;
uint32_t encDownMs = 0;
bool     encLongFired = false;

// Forward declarations (implemented in ArduleUI / ArduleStorage)
void rebuildGenreOrder();
void cycleGenreSortModeAndKeepSelection();
void prewarmPatternIndexOnce();
// ADP v2.2 header (논리 구조)
struct ADPHeader {
  char    magic[4];
  uint8_t version;
  uint8_t gridCode;
  uint8_t length;
  uint8_t slots;
  uint16_t ppqn;
  uint8_t swing;
  uint16_t tempo;
  uint8_t reserved;
  uint16_t crc16;
  uint32_t payloadBytes;
};

// 12 slots -> GM drum note
const uint8_t ADP_SLOT_NOTE[12] = {
  36, // 0: Kick
  38, // 1: Snare
  42, // 2: Closed HH
  46, // 3: Open HH
  45, // 4: Low Tom
  47, // 5: Mid Tom
  50, // 6: High Tom
  51, // 7: Ride
  49, // 8: Crash
  37, // 9: Rim
  39, // 10: Clap
  44  // 11: Pedal HH
};

// ADP payload buffer (최대 512바이트)
static uint8_t adpPayload[512];

// PATTERNS 모드 커서
int16_t patGenreCursor = 0;
int16_t patListCursor  = 0;
uint8_t currentGenreIndex = 0;

// SONGS 목록
const uint8_t MAX_SONGS = 48;
struct SongInfo {
  char base[FILEBASE_LEN];
  char typeChar; // 'm' for .MID, 'a' for .ADS (display hint)
  bool isAds;
};

SongInfo drumSongs[MAX_SONGS];
SongInfo multiSongs[MAX_SONGS];

// ===== INTERNAL MODE (Built-in patterns) =====
// These symbols are defined in ArduleInternal_*.ino, which may be concatenated
// after this main file by the Arduino build system. Forward declarations keep
// compilation order-independent.
extern uint8_t internalCursor;
// When true, PAT_LIST/PAT_SINGLE screens browse built-in (flash) patterns instead of SD patterns.
bool internalBrowserActive = false;
extern bool internalModePlaying;
void startInternalPatternPlayback(uint8_t patternId);
void stopAllPlaybackAndReset(bool toIdle);


// ===== SETTINGS (Module / Metronome Sound) =====
enum ModuleType : uint8_t {
  MODULE_SAM9703 = 0,
  MODULE_SC8820  = 1
};

uint8_t currentModuleType  = MODULE_SAM9703;
uint8_t settingsCursor     = 0;  // 0: Module Type, 1: Metronome Sound
uint8_t settingsMetroFocus = 0;  // 0: Beat, 1: Accent

// Metronome sound (GM drum note numbers on channel 10)
uint8_t metroBeatNote      = 37; // default Side Stick
uint8_t metroAccentNote    = 56; // default Cowbell

// test playback while editing metronome sound
bool     metroTestRunning  = false;
bool     metroTestIsAccent = false;
uint32_t metroTestNextMs   = 0;
const uint16_t METRO_TEST_BPM = 120;

// Metronome config/state (moved from engine module)
enum MetroEditMode : uint8_t {
  METRO_EDIT_BPM = 0,
  METRO_EDIT_SIG,
  METRO_EDIT_ACCENT
};

uint16_t metroBpm            = 120;
uint8_t  metroBeatsPerCycle  = 4;
bool     metroAccentEnabled  = true;
bool     metroRunning        = false;

uint32_t metroNextBeatMs     = 0;
uint8_t  metroBeatIndex      = 0;

MetroEditMode metroEditMode  = METRO_EDIT_BPM;

// allowed time signatures (beats per bar)
const uint8_t METRO_SIGS[] = { 2, 3, 4, 5, 7 };
const uint8_t METRO_SIG_COUNT = sizeof(METRO_SIGS) / sizeof(METRO_SIGS[0]);
uint8_t metroSigIndex = 2; // default -> 4/4

// PARAM MENU (DrumKit / Reverb) state
uint8_t  paramFocus         = 0;    // 0: DrumKit, 1: Reverb
int16_t  currentDrumKitIndex= 0;    // index into module-specific kit table
uint8_t  reverbLevel        = 4;    // 0..7 (mapped to CC91 0..112)
UiMode   paramReturnMode    = UIMODE_MAIN;

// EEPROM addresses
const uint8_t EEPROM_ADDR_MODULE_TYPE    = 0;
const uint8_t EEPROM_ADDR_METRO_BEAT     = 1;
const uint8_t EEPROM_ADDR_METRO_ACCENT   = 2;

void loadSettingsFromEeprom() {
  uint8_t mt = EEPROM.read(EEPROM_ADDR_MODULE_TYPE);
  if (mt > MODULE_SC8820) mt = MODULE_SAM9703;
  currentModuleType = mt;

  uint8_t bn = EEPROM.read(EEPROM_ADDR_METRO_BEAT);
  if (bn < 35 || bn > 81) bn = 37;
  metroBeatNote = bn;

  uint8_t an = EEPROM.read(EEPROM_ADDR_METRO_ACCENT);
  if (an < 35 || an > 81) an = 56;
  metroAccentNote = an;
}

void saveModuleTypeToEeprom() {
  EEPROM.update(EEPROM_ADDR_MODULE_TYPE, currentModuleType);
}

void saveMetronomeNotesToEeprom() {
  EEPROM.update(EEPROM_ADDR_METRO_BEAT,   metroBeatNote);
  EEPROM.update(EEPROM_ADDR_METRO_ACCENT, metroAccentNote);
}

uint8_t drumCount  = 0;
uint8_t multiCount = 0;

// SONG list overflow indicator (shown in SONG file list screen)
uint32_t songListFullUntilMs = 0;

// Current song type (set by buildCurrentSongFilePath)
bool currentSongIsADS = false;

// ADS v0.1 header/state
uint16_t adsBpm = 120;
uint16_t adsPpq = 480;
uint8_t  adsChannel = 9; // default drum ch10 (0-based 9)
uint32_t adsEventCount = 0;
uint32_t adsEventsRead  = 0;

int16_t songsRootCursor = 0;
int16_t songsFileCursor = 0;

// PREVIEW 상태
int16_t previewBpm = 120;// Update previewBpm from the currently selected SONG file (.MID tempo meta or .ADS header BPM).
void updateSongPreviewBpm() {
  // Clear previous value to avoid showing stale BPM when file open/sniff fails.
  previewBpm = 0;

  char path[64];
  if (!buildCurrentSongFilePath(path, sizeof(path))) return;

  SongInfo *arr   = (songsRootCursor == 0) ? drumSongs : multiSongs;
  uint8_t   count = (songsRootCursor == 0) ? drumCount  : multiCount;
  if (count == 0) return;
  if (songsFileCursor < 0) songsFileCursor = 0;
  if (songsFileCursor >= (int16_t)count) songsFileCursor = count - 1;

  uint16_t bpm = 0;
  if (readSongBpmFromPath(path, arr[songsFileCursor].isAds, bpm)) {
    if (bpm < 20) bpm = 20;
    if (bpm > 300) bpm = 300;
    previewBpm = (int16_t)bpm;
  }
}


// PREVIEW ALL 모드
bool     previewAllMode = false;
uint8_t  previewLoopCount = 0;
const uint8_t PREVIEW_LOOPS_PER_PATTERN = 2;

// 롱프레스 검출 구조체
struct LongPressState {
  bool     wasDown;
  uint32_t downMs;
};

const uint16_t LONG_PRESS_MS = 800;

// 인코더, METRO 버튼 롱프레스 상태
LongPressState lpEnc;
LongPressState lpMetro;
LongPressState lpInternal;

// 디바운스 래치
bool latchEncBtn=false, latchPlay=false, latchStop=false, latchInternal=false, latchMetro=false;
bool latchBpmUp=false, latchBpmDn=false;

// 인코더
volatile int16_t g_encDelta = 0;

// 버튼 피드백 LED
uint32_t btnLedOffAt = 0;
const uint16_t BTN_LED_MS = 40;

// One-time SD/INDEX prewarm trigger.
// We run the prewarm right after entering the Patterns UI (genre screen),
// so the first user click inside the Patterns UI stays responsive.
static bool pendingIndexPrewarm = false;
static bool patternsFreshEntry = false;// True only right after entering Patterns from Main
static uint8_t lastGenreForList = 255;// Used to decide whether to restore or reset patListCursor

// SD 상태
bool sdOK = false;

//////////////////// 공통 유틸 ////////////////////

// (다른 파일에 구현된 함수 프로토타입들이 여기 들어있다고 가정)


// Beat/BPM 관련


//////////////////// Setup ////////////////////
void setup() {
  pinMode(ENC_A_PIN, INPUT_PULLUP);
  pinMode(ENC_B_PIN, INPUT_PULLUP);
  pinMode(ENC_BTN_PIN, INPUT_PULLUP);

  pinMode(BTN_PLAY,     INPUT_PULLUP);
  pinMode(BTN_INTERNAL, INPUT_PULLUP);
  pinMode(BTN_STOP,     INPUT_PULLUP);
  pinMode(BTN_BPM_UP,   INPUT_PULLUP);
  pinMode(BTN_BPM_DN,   INPUT_PULLUP);
  pinMode(BTN_METRO,    INPUT_PULLUP);

  pinMode(LED_TX, OUTPUT);
  pinMode(LED_A0, OUTPUT);
  pinMode(LED_A1, OUTPUT);
  pinMode(LED_A2, OUTPUT);
  digitalWrite(LED_TX, LOW);
  digitalWrite(LED_A0, LOW);
  digitalWrite(LED_A1, LOW);
  digitalWrite(LED_A2, LOW);

  loadSettingsFromEeprom();

  Wire.begin();
  lcd.begin(LCD_COLS, LCD_ROWS);
  lcd.backlight();
  lcd.createChar(CHAR_INF, charInf);
  lcd.createChar(CHAR_PLAY, charPlay);
  lcd.createChar(CHAR_UP, charUp);
  lcd.createChar(CHAR_DOWN, charDown);

  lcdPrintLines(F("Nano Ardule v2.5"), F(" Ready to Play! "));
  delay(1000);

  if(SD.begin(SD_CS_PIN)) {
    sdOK = true;
  } else {
    sdOK = false;
    lcdPrintLines(F("SD INIT FAIL   "), F("INTERNAL MODE  "));
    delay(1000);
    uiMode = UIMODE_INTERNAL;
  }

  if(sdOK) {
    loadPatternIndexFile();
    loadSongsFromFolder("/SONGS/DRUM",  drumSongs,  drumCount);
    loadSongsFromFolder("/SONGS/MULTI", multiSongs, multiCount);
  }

  attachInterrupt(digitalPinToInterrupt(ENC_A_PIN), handleEncoderAInterrupt, CHANGE);

  if(!sdOK) {
    uiMode = UIMODE_INTERNAL;
    showInternalModeScreen();
  } else {
    uiMode = UIMODE_MAIN;
    mainCursor = 0;
    previewBpm = 120;
    showMainMenuScreen();
  }

  MIDI_SERIAL.begin(31250);
}

//////////////////// Loop ////////////////////
void loop() {
  int16_t delta = 0;
  noInterrupts();
  delta = g_encDelta;
  g_encDelta = 0;
  interrupts();

  uint32_t nowMs = millis();

bool encClick      = readButtonClick(ENC_BTN_PIN, latchEncBtn);
bool playClick     = readButtonClick(BTN_PLAY,    latchPlay);
bool stopClick     = readButtonClick(BTN_STOP,    latchStop);
bool internalClick = readButtonClick(BTN_INTERNAL,latchInternal);
bool bpmUpClick    = readButtonClick(BTN_BPM_UP,  latchBpmUp);
bool bpmDnClick    = readButtonClick(BTN_BPM_DN,  latchBpmDn);
// A6 (BTN_METRO): short click on release (< LONG_PRESS_MS), so it won't fire on long-press
bool metroClick    = readButtonReleaseClick(BTN_METRO, latchMetro, metroDownMs, nowMs, LONG_PRESS_MS);


  if(btnLedOffAt && nowMs >= btnLedOffAt) {
    digitalWrite(LED_A0, LOW);
    btnLedOffAt = 0;
  }

  if(txLedOffAtMs && nowMs >= txLedOffAtMs) {
    digitalWrite(LED_TX, LOW);
    txLedOffAtMs = 0;
  }

  if(metroAccentOffAtMs && nowMs >= metroAccentOffAtMs) {
    digitalWrite(LED_A0, LOW);
    metroAccentOffAtMs = 0;
  }

  serviceBeatEngine();
  servicePatternPlayback();
  serviceSongPlayback();
  updateMetronome();

  bool encLong = false;
  // Encoder long-press: fire ON-HOLD (not on release), once per press.
  // NOTE: Encoder click is handled separately; long-press should NOT require release.
  bool encDownNow = (digitalRead(ENC_BTN_PIN) == LOW);
  if (encDownNow) {
    if (encDownMs == 0) {
      encDownMs = nowMs;
      encLongFired = false;
    } else if (!encLongFired && (nowMs - encDownMs) >= LONG_PRESS_MS) {
      encLong = true;
      encLongFired = true;
    }
  } else {
    encDownMs = 0;
    encLongFired = false;
  }
  bool metroLong    = checkLongPressState(BTN_METRO,     lpMetro, nowMs);
  bool internalLong = checkLongPressState(BTN_INTERNAL,  lpInternal, nowMs);

  // D5 long-press: jump to INTERNAL (emergency) pattern browser.
  // Works from any screen; does not auto-start playback.
  if(internalLong && !internalBrowserActive) {
    indicateButtonFeedback();
    stopAllPlaybackAndReset(true);
    internalModePlaying = false;
    internalCursor = 0;
    internalBrowserActive = true;
    uiMode = UIMODE_PAT_LIST;
        if (patternsFreshEntry) patListCursor = 0;
        patternsFreshEntry = false;
        showPatternListScreen();
  }

  if(metroLong && uiMode != UIMODE_METRO) {
    indicateButtonFeedback();
    stopAllPlaybackAndReset(true);
    prevTopMode = uiMode;
    setMetronomeConfig(metroBpm, metroBeatsPerCycle, metroAccentEnabled);
    startMetronome();
    uiMode = UIMODE_METRO;
    showMetronomeScreen();
  }

  // Enter INTERNAL mode only from top menu to keep UX predictable.
  if(internalClick && uiMode == UIMODE_MAIN) {
    indicateButtonFeedback();
    stopAllPlaybackAndReset(true);
    internalModePlaying = false;
    internalCursor = 0;
    internalBrowserActive = true;
    uiMode = UIMODE_PAT_LIST;
    patListCursor = 0;
    showPatternListScreen();
  }

  switch(uiMode) {
    case UIMODE_MAIN:
      if(delta != 0) {
        mainCursor += (delta > 0 ? 1 : -1);
        if(mainCursor < 0) mainCursor = 0;
        if(mainCursor >= (int16_t)MM_COUNT) mainCursor = MM_COUNT - 1;
        showMainMenuScreen();
      }
      // D7/D8 (-/+) navigate by 1 in list/selection screens.
      if(bpmUpClick || bpmDnClick) {
        mainCursor += (bpmUpClick ? 1 : -1);
        if(mainCursor < 0) mainCursor = 0;
        if(mainCursor >= (int16_t)MM_COUNT) mainCursor = MM_COUNT - 1;
        showMainMenuScreen();
      }
      if(encClick) {
        indicateButtonFeedback();
        if(mainCursor == MM_PATTERNS) {
          uiMode = UIMODE_PAT_GEN;
          patGenreCursor = 0;
          currentGenreIndex = 0;
          rebuildGenreOrder();
          patternsFreshEntry = true; // entering Patterns UI from top
          lastGenreForList = 255; // force list cursor reset on first genre selection
          // Prewarm SD access once right after entering the Patterns UI.
          // This shifts the one-time cold SD/INDEX cost away from the first click
          // inside the Patterns UI (e.g., selecting a genre).
          pendingIndexPrewarm = true;
          showPatternGenreScreen();
        } else if(mainCursor == MM_SONGS) {
          uiMode = UIMODE_SONGS_ROOT;
          songsRootCursor = 0;
          showSongsRootScreen();
        } else if(mainCursor == MM_METRONOME) {
          prevTopMode = UIMODE_MAIN;
          setMetronomeConfig(metroBpm, metroBeatsPerCycle, metroAccentEnabled);
          startMetronome();
          uiMode = UIMODE_METRO;
          showMetronomeScreen();
        } else if(mainCursor == MM_INTERNAL) {
          stopAllPlaybackAndReset(true);
          internalModePlaying = false;
          internalCursor = 0;
          internalBrowserActive = true;
          uiMode = UIMODE_PAT_LIST;
          patListCursor = 0;
          showPatternListScreen();
        } else if(mainCursor == MM_SETTINGS) {
          uiMode = UIMODE_SETTINGS;
          settingsUiMode = SETTINGS_UI_MENU;
          settingsCursor = 0;
          showSettingsMenuScreen();
        }
      }
      break;

    case UIMODE_METRO:
      if(delta != 0) {
        if(metroEditMode == METRO_EDIT_BPM) {
          setMetronomeBpm(metroBpm + (delta > 0 ? 1 : -1));
          showMetronomeScreen();
        } else if(metroEditMode == METRO_EDIT_SIG) {
          int8_t idx = (int8_t)metroSigIndex + (delta > 0 ? 1 : -1);
          if(idx < 0) idx = 0;
          if(idx >= (int8_t)METRO_SIG_COUNT) idx = METRO_SIG_COUNT - 1;
          metroSigIndex = (uint8_t)idx;
          setMetronomeBeatsPerCycle(METRO_SIGS[metroSigIndex]);
          showMetronomeScreen();
        } else if(metroEditMode == METRO_EDIT_ACCENT) {
          setMetronomeAccent(!metroAccentEnabled);
          showMetronomeScreen();
        }
      }
      if(encClick) {
        indicateButtonFeedback();
        if(metroEditMode == METRO_EDIT_BPM)      metroEditMode = METRO_EDIT_SIG;
        else if(metroEditMode == METRO_EDIT_SIG) metroEditMode = METRO_EDIT_ACCENT;
        else                                     metroEditMode = METRO_EDIT_BPM;
        showMetronomeScreen();
      }
      if(bpmUpClick) {
        setMetronomeBpm(metroBpm + 1);
        showMetronomeScreen();
      }
      if(bpmDnClick) {
        setMetronomeBpm(metroBpm - 1);
        showMetronomeScreen();
      }
      if(stopClick) {
        indicateButtonFeedback();
        stopMetronome();
        uiMode = prevTopMode;
        if(uiMode == UIMODE_MAIN) {
          showMainMenuScreen();
        } else if(uiMode == UIMODE_INTERNAL) {
          showInternalModeScreen();
        } else if(uiMode == UIMODE_PAT_GEN) {
          showPatternGenreScreen();
        } else if(uiMode == UIMODE_PAT_LIST) {
          showPatternListScreen();
        } else if(uiMode == UIMODE_SONGS_ROOT) {
          showSongsRootScreen();
        } else if(uiMode == UIMODE_SONGS_FILELIST) {
          showSongsFileListScreen();
        }
      }
      break;

    case UIMODE_SETTINGS:
      if(settingsUiMode == SETTINGS_UI_MENU) {
        if(delta != 0) {
          if(delta > 0) settingsCursor++;
          else          settingsCursor--;
          if(settingsCursor < 0) settingsCursor = 0;
          if(settingsCursor > 1) settingsCursor = 1;
          showSettingsMenuScreen();
        }
        if(bpmUpClick || bpmDnClick) {
          settingsCursor += (bpmUpClick ? 1 : -1);
          if(settingsCursor < 0) settingsCursor = 0;
          if(settingsCursor > 1) settingsCursor = 1;
          showSettingsMenuScreen();
        }
        if(encClick) {
          indicateButtonFeedback();
          if(settingsCursor == 0) {
            settingsUiMode = SETTINGS_UI_EDIT_MODULE;
            showSettingsModuleScreen();
          } else {
            settingsUiMode = SETTINGS_UI_EDIT_METRO_SOUND;
            settingsMetroFocus = 0;
            metroTestRunning  = true;
            metroTestIsAccent = false;
            metroTestNextMs   = 0;
            showSettingsMetronomeSoundScreen();
          }
        }
        if(stopClick) {
          indicateButtonFeedback();
          metroTestRunning = false;
          uiMode = UIMODE_MAIN;
          showMainMenuScreen();
        }
      } else if(settingsUiMode == SETTINGS_UI_EDIT_MODULE) {
        if(delta != 0) {
          if(delta > 0 || delta < 0) {
            currentModuleType = (currentModuleType == MODULE_SAM9703) ? MODULE_SC8820 : MODULE_SAM9703;
          }
          showSettingsModuleScreen();
        }
        if(encClick) {
          indicateButtonFeedback();
          saveModuleTypeToEeprom();
          lcdPrintLines("Module saved   ", (currentModuleType == MODULE_SAM9703) ? "SAM9703        " : "SC-8820       ");
          delay(600);
          showSettingsModuleScreen();
        }
        if(stopClick) {
          indicateButtonFeedback();
          settingsUiMode = SETTINGS_UI_MENU;
          showSettingsMenuScreen();
        }
      } else if(settingsUiMode == SETTINGS_UI_EDIT_METRO_SOUND) {
        uint32_t nowMs2 = millis();
        if(metroTestRunning && nowMs2 >= metroTestNextMs) {
          uint8_t note = metroTestIsAccent ? metroAccentNote : metroBeatNote;
          sendMidiMessage3(0x99, note, 110);
          uint32_t intervalMs = (uint32_t)(60000UL / METRO_TEST_BPM);
          if(intervalMs < 60) intervalMs = 60;
          metroTestNextMs = nowMs2 + intervalMs;
        }

        if(delta != 0) {
          if(settingsMetroFocus == 0) {
            int16_t v = (int16_t)metroBeatNote + (delta > 0 ? 1 : -1);
            if(v < 35) v = 35;
            if(v > 81) v = 81;
            metroBeatNote = (uint8_t)v;
          } else {
            int16_t v = (int16_t)metroAccentNote + (delta > 0 ? 1 : -1);
            if(v < 35) v = 35;
            if(v > 81) v = 81;
            metroAccentNote = (uint8_t)v;
          }
          metroTestRunning  = true;
          metroTestIsAccent = (settingsMetroFocus == 1);
          metroTestNextMs   = 0;
          showSettingsMetronomeSoundScreen();
        }
        if(encClick) {
          indicateButtonFeedback();
          settingsMetroFocus = (settingsMetroFocus == 0) ? 1 : 0;
          metroTestIsAccent  = (settingsMetroFocus == 1);
          metroTestRunning   = true;
          metroTestNextMs    = 0;
          showSettingsMetronomeSoundScreen();
        }
        if(stopClick) {
          indicateButtonFeedback();
          metroTestRunning = false;
          saveMetronomeNotesToEeprom();
          settingsUiMode = SETTINGS_UI_MENU;
          showSettingsMenuScreen();
        }
      }
      break;

    case UIMODE_PAT_GEN:
      // One-time SD/INDEX prewarm (SD mode only).
      // Runs without button feedback to avoid "long LED" perception.
      if(pendingIndexPrewarm && !internalBrowserActive) {
        pendingIndexPrewarm = false;
        prewarmPatternIndexOnce();
      }
      if(delta != 0) {
        patGenreCursor += (delta > 0 ? 1 : -1);
        if(patGenreCursor < 0) patGenreCursor = 0;
        if(patGenreCursor >= (int16_t)genreCount) patGenreCursor = genreCount-1;
        showPatternGenreScreen();
      }
      if(bpmUpClick || bpmDnClick) {
        patGenreCursor += (bpmUpClick ? 1 : -1);
        if(patGenreCursor < 0) patGenreCursor = 0;
        if(patGenreCursor >= (int16_t)genreCount) patGenreCursor = genreCount-1;
        showPatternGenreScreen();
      }
      // A6 short click: cycle genre sort order (N↓ -> N↑ -> A→Z -> Z→A)
      if(metroClick) {
        indicateButtonFeedback();
        cycleGenreSortModeAndKeepSelection();
      }
      if(encClick) {
        indicateButtonFeedback();
        uint8_t selGenre = genreOrder[(uint8_t)patGenreCursor];
        currentGenreIndex = selGenre;
        uiMode = UIMODE_PAT_LIST;
        if (patternsFreshEntry || selGenre != lastGenreForList) patListCursor = 0;
        lastGenreForList = selGenre;
        patternsFreshEntry = false;
        showPatternListScreen();
      }
      if(stopClick) {
        indicateButtonFeedback();
        patternsFreshEntry = false;
        uiMode = UIMODE_MAIN;
        showMainMenuScreen();
      }
      break;

    case UIMODE_PAT_LIST:
      if(delta != 0) {
        patListCursor += (delta > 0 ? 1 : -1);
        if (internalBrowserActive) {
          int16_t cnt = (int16_t)EMERGENCY_PATTERN_COUNT;
          if (patListCursor < 0) patListCursor = 0;
          if (cnt > 0 && patListCursor >= cnt) patListCursor = cnt - 1;
          internalCursor = (uint8_t)patListCursor;
        } else if(genreCount > 0) {
          uint8_t cnt = genres[currentGenreIndex].count;
          if(patListCursor < 0) patListCursor = 0;
          if(patListCursor >= (int16_t)cnt) patListCursor = cnt-1;
        }
        showPatternListScreen();
      }
      if(bpmUpClick || bpmDnClick) {
        patListCursor += (bpmUpClick ? 1 : -1);
        if (internalBrowserActive) {
          int16_t cnt = (int16_t)EMERGENCY_PATTERN_COUNT;
          if (patListCursor < 0) patListCursor = 0;
          if (cnt > 0 && patListCursor >= cnt) patListCursor = cnt - 1;
          internalCursor = (uint8_t)patListCursor;
        } else if(genreCount > 0) {
          uint8_t cnt = genres[currentGenreIndex].count;
          if(patListCursor < 0) patListCursor = 0;
          if(patListCursor >= (int16_t)cnt) patListCursor = cnt-1;
        }
        showPatternListScreen();
      }
      if(encClick) {
        indicateButtonFeedback();
        uiMode = UIMODE_PAT_SINGLE;
        playState = PLAYSTATE_IDLE;
        previewAllMode   = false;
        previewLoopCount = 0;
        if (internalBrowserActive) {
          internalCursor = (uint8_t)patListCursor;
          internalModePlaying = false; // READY only, do not auto-play
        }
        showPatternPlayScreen();
      }
      if(playClick) {
        if (!internalBrowserActive) {
          // SD pattern list: start preview-all mode (original behavior)
          indicateButtonFeedback();
          startAutoPatternPreview();
        }
      }
      if(stopClick) {
        indicateButtonFeedback();
        if (internalBrowserActive) {
          // INTERNAL browser: STOP returns to Main Menu (no genre screen)
          internalBrowserActive = false;
          uiMode = UIMODE_MAIN;
          showMainMenuScreen();
        } else {
          uiMode = UIMODE_PAT_GEN;
          showPatternGenreScreen();
        }
      }
      break;

    case UIMODE_PAT_SINGLE:
      // --- 인코더: 항상 BPM 조절 ---
      if (delta != 0) {
        int16_t step = (delta > 0 ? 1 : -1);
        previewBpm += step;
        if (previewBpm < 20)  previewBpm = 20;
        if (previewBpm > 300) previewBpm = 300;
        updateBeatTimingFromBpm();
        showPatternPlayScreen();
      }

      // 인코더 롱프레스 → PARAM MENU (DrumKit / Reverb)
      if(encLong) {
        indicateButtonFeedback();
        paramReturnMode = uiMode;
        paramFocus      = 0;
        uiMode          = UIMODE_PARAM_MENU;
        showParamMenuScreen();
      }

      // --- PLAY 버튼 (A3) 동작 ---
      if (playClick) {
        indicateButtonFeedback();

        if (previewAllMode) {
          // 프리뷰 ALL 모드: 재생 / 일시정지 토글
          if (playState == PLAYSTATE_PLAYING) {
            playState = PLAYSTATE_PAUSED;
          } else if (playState == PLAYSTATE_PAUSED) {
            playState = PLAYSTATE_PLAYING;
          } else {
            // IDLE이면 프리뷰 ALL 다시 시작
            startAutoPatternPreview();
          }
        } else {
          // 단일 패턴 모드: 기존 동작 유지 (PLAY / STOP)
          if (playState == PLAYSTATE_IDLE) {
            if (internalBrowserActive) {
              // Internal patterns: do NOT auto-play on list entry; play starts only here.
              startInternalPatternPlayback(internalCursor);
              internalModePlaying = true;
            } else {
              startSinglePatternPlayback();
            }
          } else {
            stopAllPlaybackAndReset(true);
            if (internalBrowserActive) internalModePlaying = false;
          }
        }

        // 화면은 항상 공통 함수로 갱신
        showPatternPlayScreen();
      }

      // --- 프리뷰 ALL 모드일 때: D7/D8로 패턴 넘기기 ---
      if (previewAllMode) {
        if (bpmUpClick || bpmDnClick) {
          int16_t dir = 0;
          if (bpmUpClick) dir = 1;
          if (bpmDnClick) dir = -1;

          if (dir != 0 && genreCount > 0) {
            uint8_t cnt = genres[currentGenreIndex].count;
            if (cnt > 0) {
              patListCursor += dir;
              if (patListCursor < 0)             patListCursor = 0;
              if (patListCursor >= (int16_t)cnt) patListCursor = cnt - 1;
              previewLoopCount = 0;
              showPatternPlayScreen();
              startSinglePatternPlayback();
            }
          }
        }
      }
      // --- 단일 패턴 모드일 때: D7/D8로도 BPM 변경 ---
      else {
        if(bpmUpClick) {
          indicateButtonFeedback();
          previewBpm++;
          if (previewBpm > 300) previewBpm = 300;
          updateBeatTimingFromBpm();
          showPatternPlayScreen();
        }
        if(bpmDnClick) {
          indicateButtonFeedback();
          previewBpm--;
          if(previewBpm < 20) previewBpm = 20;
          updateBeatTimingFromBpm();
          showPatternPlayScreen();
        }
      }

      // --- STOP 버튼 ---
      if(stopClick) {
        indicateButtonFeedback();
        previewAllMode   = false;
        previewLoopCount = 0;
        stopAllPlaybackAndReset(true);

        // Return to the correct list depending on source
        if (internalBrowserActive) {
          internalModePlaying = false;
          uiMode = UIMODE_PAT_LIST;
          // keep patListCursor/internalCursor as-is
          showPatternListScreen();
        } else {
          uiMode = UIMODE_PAT_LIST;
          // keep patListCursor as-is
          showPatternListScreen();
        }
      }
      break;

    case UIMODE_SONGS_ROOT:
      if(delta != 0) {
        songsRootCursor += (delta > 0 ? 1 : -1);
        if(songsRootCursor < 0) songsRootCursor = 0;
        if(songsRootCursor > 1) songsRootCursor = 1;
        showSongsRootScreen();
      }
      if(bpmUpClick || bpmDnClick) {
        songsRootCursor += (bpmUpClick ? 1 : -1);
        if(songsRootCursor < 0) songsRootCursor = 0;
        if(songsRootCursor > 1) songsRootCursor = 1;
        showSongsRootScreen();
      }
      if(encClick) {
        indicateButtonFeedback();
        uiMode = UIMODE_SONGS_FILELIST;
        songsFileCursor = 0;
        showSongsFileListScreen();
        updateSongPreviewBpm();
      }
      if(stopClick) {
        indicateButtonFeedback();
        uiMode = UIMODE_MAIN;
        showMainMenuScreen();
      }
      break;

    case UIMODE_SONGS_FILELIST:
      if(delta != 0) {
        songsFileCursor += (delta > 0 ? 1 : -1);
        {
          uint8_t count = (songsRootCursor == 0) ? drumCount : multiCount;
          if(count > 0) {
            if(songsFileCursor < 0) songsFileCursor = 0;
            if(songsFileCursor >= (int16_t)count) songsFileCursor = count-1;
          }
        }
        showSongsFileListScreen();
      }
      if(bpmUpClick || bpmDnClick) {
        songsFileCursor += (bpmUpClick ? 1 : -1);
        {
          uint8_t count = (songsRootCursor == 0) ? drumCount : multiCount;
          if(count > 0) {
            if(songsFileCursor < 0) songsFileCursor = 0;
            if(songsFileCursor >= (int16_t)count) songsFileCursor = count-1;
          }
        }
        showSongsFileListScreen();
      }

      if (encClick) {
        indicateButtonFeedback();
        uiMode = UIMODE_SONG_PLAY;
        playState = PLAYSTATE_IDLE;
        updateSongPreviewBpm();
        showSongPlayScreen();
      }

      if(playClick) {
        // SONG LIST에서는 바로 재생 시작 X
      }

      if(stopClick) {
        indicateButtonFeedback();
        uiMode = UIMODE_SONGS_ROOT;
        showSongsRootScreen();
      }
      break;

    case UIMODE_INTERNAL:
      if(delta != 0) {
        int16_t v = (int16_t)internalCursor + (delta > 0 ? 1 : -1);
        if(v < 0) v = 0;
        if(v >= (int16_t)EMERGENCY_PATTERN_COUNT) v = (int16_t)EMERGENCY_PATTERN_COUNT - 1;
        internalCursor = (uint8_t)v;
        showInternalModeScreen();
      }

      // Play selected built-in pattern
      if(playClick || encClick) {
        indicateButtonFeedback();
        if(internalModePlaying && playState == PLAYSTATE_PLAYING) {
          // Stop
          stopAllPlaybackAndReset(true);
          internalModePlaying = false;
        } else {
          startInternalPatternPlayback(internalCursor);
          uiMode = UIMODE_PAT_SINGLE;
          showPatternPlayScreen();
        }
        // stay on Pattern Play screen
}

      if(stopClick) {
        indicateButtonFeedback();
        if(internalModePlaying) {
          stopAllPlaybackAndReset(true);
          internalModePlaying = false;
          showInternalModeScreen();
        } else {
          uiMode = UIMODE_MAIN;
          showMainMenuScreen();
        }
      }
      break;

    case UIMODE_SONG_PLAY:
      if(encLong) {
        indicateButtonFeedback();
        paramReturnMode = uiMode;
        paramFocus = 0;
        uiMode = UIMODE_PARAM_MENU;
        showParamMenuScreen();
      }

      if (playClick) {
        indicateButtonFeedback();
        if (playState == PLAYSTATE_IDLE) {
          startSongPlayback();
        } else if (playState == PLAYSTATE_PLAYING) {
          songPauseStartUs = micros();
          playState        = PLAYSTATE_PAUSED;
        } else if (playState == PLAYSTATE_PAUSED) {
          uint32_t nowUs       = micros();
          uint32_t pausedSpan  = nowUs - songPauseStartUs;
          nextEventUs += pausedSpan;
          playState    = PLAYSTATE_PLAYING;
        }
        showSongPlayScreen();
      }

      if (bpmUpClick) {
        indicateButtonFeedback();
        previewBpm++;
        showSongPlayScreen();
      }
      if (bpmDnClick) {
        indicateButtonFeedback();
        previewBpm--;
        if (previewBpm < 20) previewBpm = 20;
        showSongPlayScreen();
      }

      if (stopClick) {
        indicateButtonFeedback();
        stopAllPlaybackAndReset(true);
        uiMode = UIMODE_SONGS_FILELIST;
        showSongsFileListScreen();
      }
      break;

    case UIMODE_PARAM_MENU:
      if(delta != 0) {
        if(paramFocus == 0) {
          int16_t dir = (int16_t)(delta > 0 ? 1 : -1);
          currentDrumKitIndex += dir;
          int16_t maxIdx = 0;
          if(currentModuleType == MODULE_SAM9703) {
            maxIdx = (int16_t)SAM9703_KITS_COUNT - 1;
          } else {
            maxIdx = (int16_t)SC8820_KITS_COUNT - 1;
          }
          if(currentDrumKitIndex < 0) currentDrumKitIndex = 0;
          if(currentDrumKitIndex > maxIdx) currentDrumKitIndex = maxIdx;
          applyCurrentDrumKitToModule();
        } else {
          if(delta > 0 && reverbLevel < 7) reverbLevel++;
          if(delta < 0 && reverbLevel > 0) reverbLevel--;
          applyCurrentReverbToModule();
        }
        showParamMenuScreen();
      }

      if(encClick) {
        indicateButtonFeedback();
        paramFocus = (paramFocus == 0) ? 1 : 0;
        showParamMenuScreen();
      }

      if(stopClick) {
        indicateButtonFeedback();
        uiMode = paramReturnMode;
        if(uiMode == UIMODE_PAT_SINGLE) {
          showPatternPlayScreen();
        } else if(uiMode == UIMODE_SONG_PLAY) {
          showSongPlayScreen();
        } else if(uiMode == UIMODE_INTERNAL) {
          showInternalModeScreen();
        } else if(uiMode == UIMODE_MAIN) {
          showMainMenuScreen();
        } else {
          showMainMenuScreen();
        }
      }
      break;
  }
}