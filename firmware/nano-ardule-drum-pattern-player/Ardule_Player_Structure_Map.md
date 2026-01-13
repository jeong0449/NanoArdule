# Nano Ardule Drum Pattern Player (Firmware) — Structure Map

**Last updated:** 2026-01-12

>
> Target board (per sketch header): **Arduino Nano Every (ATmega4809)**.  
> Key modes: **ADP pattern playback** (2-bar loop engine) + **SONG playback** (Type 0 MIDI + ADS v0.1).

---

## 1. File/Module Tree

```text
nano-ardule-drum-pattern-player/
├─ nano-ardule-drum-pattern-player.ino        # sketch entry: globals, setup(), loop(), state enums
├─ ArduleEngine_113025_v2_5.ino               # timing + playback engines (pattern + song) + MIDI send
├─ ArduleStorage_111925_v2_5.ino              # SD I/O: index load, ADP parse->event buffer, song file open
├─ ArduleUI_113025_v2_5.ino                   # LCD UI screens + settings/params rendering
├─ ArduleInput_111925_v2_5.ino                # buttons/encoder input handling
└─ GMDrumNames.h                              # GM drum note -> 8-char name lookup
```

---

## 2. High-level Architecture

### 2.1 Core concepts

- **UI state machine**
  - `UiMode` drives which screen is active (Main / Pattern / Songs / Metronome / Settings / etc.).
- **Playback state**
  - `PlayState`: `IDLE / PLAYING / PAUSED`
  - `PlaySource`: `NONE / PATTERN / SONG`
- **Two playback engines**
  - **Pattern engine**: absolute-time (tick-based) loop with a single active pattern buffer.
  - **Song engine**: reads Type 0 MIDI events from a file and schedules them using `usPerTick`.

### 2.2 Data flow (runtime)

```text
[Input (buttons/encoder)]
          │
          ▼
[UI state machine] ────────► (select file / change params / start-stop)
          │
          ▼
[Storage: SD read] ────────► (load ADP -> PatternEvent[], open MIDI song file)
          │
          ▼
[Engine: timing + schedulers] ─► [MIDI OUT] + [metronome/beat LEDs]
```

---

## 3. Key Global Data Structures (defined in `nano-ardule-drum-pattern-player.ino`)

### 3.1 UI / Playback state

- `UiMode uiMode`, `UiMode prevTopMode`
- `SettingsUiMode settingsUiMode`
- `PlayState playState`
- `PlaySource playSource`

### 3.2 Pattern engine buffer (single active buffer)

```cpp
const uint16_t PAT_MAX_EVENTS = 128;

struct PatternEvent {
  uint16_t tick;   // absolute tick from loop start
  uint8_t  status; // MIDI status byte (e.g., 0x99 for CH10 note on)
  uint8_t  d1;     // data1
  uint8_t  d2;     // data2 (velocity)
};

struct PatternEngineState {
  PatternEvent events[PAT_MAX_EVENTS];
  uint16_t     eventCount;
  uint16_t     eventIndex;
  uint16_t     loopLenTicks;
  uint32_t     loopStartUs;
  bool         loaded;
};

PatternEngineState patA;          // single “active only” buffer
PatternEngineState* patCur = &patA;
```

Convenience macros:
- `patEvents`, `patEventCount`, `patEventIndex`, `patLoopLenTicks`, `patLoopStartUs`, `patLoaded`

### 3.3 Fixed “2-bar beat engine” assumptions (current firmware)

```cpp
const uint8_t BEATS_PER_BAR = 4;
const uint8_t BARS_PER_LOOP = 2;
const uint8_t TOTAL_BEATS   = 8; // 4/4 * 2 bars
```

This is an important “fixed-time” assumption for the **beat LED / metronome / bar-cycle** logic.

### 3.4 ADP header (binary) representation

The sketch defines an `ADPHeader` struct with fields such as:
- `version`, `gridCode`, `length`, `slots`, `ppqn`, `swing`, `tempo`, `crc16`, `payloadBytes`
…and a slot-to-drum-note mapping table `ADP_SLOT_NOTE[12]`.

(ADP parsing and conversion to `PatternEvent[]` happens in the Storage module.)

### 3.5 Song playback timing state

Globals include:
- `midiPPQ` (default 480)
- `usPerQuarter`, `usPerTick`
- `nextEventUs`, `haveNextEvent`, `endOfTrack`, `runningStatus`
- `File playFile`, `playFileOpen`, `currentFilePath[32]`

---

## 4. Module-by-module Breakdown

## 4.1 `nano-ardule-drum-pattern-player.ino` (Entry / Orchestration)

**Role**
- Declares global state, structs, and configuration constants.
- Implements EEPROM settings load/save helpers.
- Owns `setup()` and `loop()`.

**Notable functions**
- `loadSettingsFromEeprom()`
- `saveModuleTypeToEeprom()`
- `saveMetronomeNotesToEeprom()`
- `setup()`
- `loop()`

**Typical loop responsibilities (conceptually)**
- Poll input / update UI state
- Service pattern playback when `PlaySource == PATTERN`
- Service song playback when `PlaySource == SONG`
- Update metronome/beat engine and UI repaint logic

---

## 4.2 `ArduleEngine_113025_v2_5.ino` (Timing + Playback + MIDI Out)

**Role**
- Beat engine (LED timing), metronome logic, MIDI send helpers.
- Pattern playback scheduler (absolute tick -> microseconds)
- Song playback scheduler:
  - Type 0 MIDI (delta-time events -> microseconds)
  - ADS v0.1 (absolute tick stream -> microseconds; MetaTime)

**Notable functions (names as found)**
- Beat: `updateBeatTimingFromBpm()`, `clearBeatLeds()`, `startBeatEngine()`, `stopBeatEngine()`, `serviceBeatEngine()`
- MIDI send: `sendMidiByte()`, `sendMidiMessage2()`, `sendMidiMessage3()`, `sendMidiPanic()`
- Metronome: `recalcMetronomeInterval()`, `setMetronomeConfig()`, `setMetronomeBpm()`, `setMetronomeBeatsPerCycle()`, `setMetronomeAccent()`, `startMetronome()`, `stopMetronome()`
- Song (MIDI) scheduler: includes handlers like `handleEndOfTrackEvent()` and a `serviceSongPlayback()` loop
- Song (ADS) scheduler: `openCurrentAdsSongFile()`, `serviceAdsPlayback()`, `readNextAdsEvent()`
- Pattern scheduler: `servicePatternPlayback()`

**Key outputs**
- MIDI OUT stream
- Beat LED / metronome accent LED (if used)

---

## 4.3 `ArduleStorage_111925_v2_5.ino` (SD Card I/O + Parsing)

**Role**
- Reads and parses SD-card files:
  - Pattern index (`PATTERNS/INDEX.TXT`) into `PatternInfo[]`
  - ADP binary into the in-memory `PatternEvent[]` buffer
  - Type 0 MIDI file open/read helpers for SONG mode
  - ADS v0.1 open/read helpers for SONG mode (.ADS alongside .MID)

**Notable functions (names as found)**
- String/file helpers: `trimLineEnding()`, `stripFileExtension()`, `copyTrimmed()`
- Index and lists: `loadPatternIndex()`, plus helpers for browsing
- ADP parsing: functions include reading header/payload and producing events (e.g., `loadCurrentPatternIntoMemory()`)
- Song files: `openCurrentMidiSongFile()`, `openCurrentAdsSongFile()`
- SONG UI preview: BPM sniff helpers for .MID/.ADS (`readSongBpmFromPath()`)

**Important design point**
- The firmware uses a **single active pattern buffer** (“Preview All (no preload, single pattern buffer)” per header comment).
  - This keeps RAM usage low but implies re-load costs on pattern change.

---

## 4.4 `ArduleUI_113025_v2_5.ino` (LCD UI)

**Role**
- All HD44780 LCD rendering and screen switching.
- Parameter screens (metronome, settings, module parameters).
- Pattern list and song list screens.

**Notable functions (names as found)**
- LCD primitives: `lcdPrintLines()`
- Screens: `showMetronomeScreen()`, `showSettingScreen()`, `showMainScreen()`, etc.
- Pattern UI: `showPatternListScreen()`, `showPatternPlayScreen()`
- Song UI: `showSongsRootScreen()`, `showSongsFileListScreen()`, `showSongPlayScreen()`
- Module params: `getCurrentDrumKitInfo()`, `applyCurrentDrumKitToModule()`, `applyCurrentReverbToModule()`, `showParamMenuScreen()`

---

## 4.5 `ArduleInput_111925_v2_5.ino` (Buttons / Encoder)

**Role**
- Reads buttons (click/long-press) and encoder movement.
- Provides UI feedback (beep/LED) hooks.

**Notable functions (names as found)**
- `readButtonClick()`
- `indicateButtonFeedback()`
- `checkLongPressState()`
- `handleEncoderAInterrupt()`

---

## 4.6 `GMDrumNames.h` (GM drum note naming)

**Role**
- Lookup helper returning short (8-char) names for drum notes.

**Notable function**
- `getDrumName8()`

---

## 5. “Harmony” Between ADP Pattern Mode and (Future) ADS Mode — Where to Plug In

Even if ADS does **not** reference ADP, the existing firmware architecture suggests a clean extension point:

- Keep **one Transport/Timebase** in Engine.
- Add a new “Source” beside `PATTERN` and `SONG`, e.g. `PLAY_SRC_ADS`.
- Implement `serviceAdsPlayback()` analogous to `servicePatternPlayback()` / `serviceSongPlayback()`.
- Reuse **the same MIDI send helpers** (`sendMidiMessage*`, `sendMidiPanic`) and beat/metronome outputs.

If the ADS time model differs from the current fixed `2-bar / 8-beat` assumptions, the most sensitive area is:
- beat/metronome cycle calculation (`TOTAL_BEATS` etc.)
- anything that assumes **always 2 bars** for visual/audio accents

---

## 6. Quick “Where is what?” Index

- **Main state enums & global structs**: `nano-ardule-drum-pattern-player.ino`
- **Pattern event buffer + tick scheduler**: `ArduleEngine_113025_v2_5.ino`
- **ADP decode / INDEX.TXT parsing / SD access**: `ArduleStorage_111925_v2_5.ino`
- **UI screens and menu logic**: `ArduleUI_113025_v2_5.ino`
- **Buttons/encoder**: `ArduleInput_111925_v2_5.ino`
- **Drum names**: `GMDrumNames.h`

