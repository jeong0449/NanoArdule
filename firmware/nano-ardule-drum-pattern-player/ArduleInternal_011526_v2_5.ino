// Built-in (Emergency) Pattern support
//
// Purpose:
//  - Keep a small, always-available set of patterns in flash (PROGMEM)
//  - Allow the user to browse + play them even when SD init fails
//
// Data sources:
//  - emergency_index.h    : human-readable list (genre/code/steps)
//  - emergency_payload.h  : packed 2-bit grid records

#include "emergency_index.h"
#include "emergency_payload.h"

// Externs provided by the main sketch
extern uint16_t midiPPQ;
extern int16_t previewBpm;
extern uint32_t usPerQuarter;
extern uint32_t usPerTick;

// Pattern engine state is exposed in the main sketch via macros:
//   patEvents, patEventCount, patEventIndex, patLoopLenTicks, patLoaded
// We intentionally do NOT redeclare them here, because they are macros.

extern PlaySource playSource;
extern PlayState  playState;
extern void startBeatEngine();
extern void stopAllPlaybackAndReset(bool toIdle);
extern void beginLoadedPatternPlayback();

// Public UI globals
uint8_t internalCursor = 0;
bool    internalModePlaying = false;

// Offset table (SRAM) - 42 patterns => 84 bytes
static uint16_t emergencyOffsetsRam[EMERGENCY_PATTERN_COUNT];
static bool emergencyOffsetsReady = false;

// Record format:
//  [patternId, stepsInBar] + packed 2-bit grid (EMERGENCY_SLOTS x stepsInBar)
//  bytes = 2 + ceil((EMERGENCY_SLOTS * stepsInBar * 2) / 8)
static inline uint16_t emergencyRecordSize(uint8_t stepsInBar) {
  uint16_t bits = (uint16_t)EMERGENCY_SLOTS * (uint16_t)stepsInBar * 2u;
  uint16_t bytes = (uint16_t)((bits + 7u) / 8u);
  return (uint16_t)(2u + bytes);
}

void initEmergencyOffsetsOnce() {
  if (emergencyOffsetsReady) return;

  uint16_t off = 0;
  for (uint8_t pid = 0; pid < EMERGENCY_PATTERN_COUNT; pid++) {
    emergencyOffsetsRam[pid] = off;
    uint8_t steps = pgm_read_byte(&emergencyPayload[off + 1]);
    off += emergencyRecordSize(steps);
  }
  emergencyOffsetsReady = true;
}

// Read 2-bit value from packed grid (slot-major then step):
// idx = slot*steps + step
static inline uint8_t emergencyGet2bit(uint8_t pid, uint8_t slot, uint8_t step, uint8_t stepsInBar) {
  uint16_t base = emergencyOffsetsRam[pid];
  uint16_t idx  = (uint16_t)slot * (uint16_t)stepsInBar + (uint16_t)step;
  uint16_t bit  = idx * 2u;
  uint16_t byteIndex = (uint16_t)2u + (bit >> 3);
  uint8_t  shift = (uint8_t)(bit & 7u);

  uint8_t b = pgm_read_byte(&emergencyPayload[base + byteIndex]);
  uint8_t v = (uint8_t)((b >> shift) & 0x03u);

  // If it straddles a byte boundary (shift==7), pull next byte's LSB.
  if (shift == 7u) {
    uint8_t b2 = pgm_read_byte(&emergencyPayload[base + byteIndex + 1u]);
    v = (uint8_t)(((b >> 7) | ((b2 & 0x01u) << 1)) & 0x03u);
  }
  return v;
}

bool loadInternalPatternIntoMemory(uint8_t pid) {
  initEmergencyOffsetsOnce();
  if (pid >= EMERGENCY_PATTERN_COUNT) return false;

  patEventCount   = 0;
  patEventIndex   = 0;
  patLoopLenTicks = 0;
  patLoaded       = false;

  uint16_t base = emergencyOffsetsRam[pid];
  uint8_t stepsInBar = pgm_read_byte(&emergencyPayload[base + 1]);
  if (stepsInBar == 0) return false;

  // IMPORTANT:
  // The emergency payload encodes **1 bar** patterns (variable steps per bar).
  // Map steps to ticks within a single 4/4 bar, exactly like SD-based ADP.
  // (The previous implementation incorrectly spread 1-bar grids across 2 bars,
  // which made INTERNAL playback feel slow and desynced LEDs at the start.)
  uint32_t barTicks = (uint32_t)midiPPQ * 4UL; // 1 bar (4 quarter notes)
  if (barTicks > 65535UL) barTicks = 65535UL;
  uint32_t stepTicks = barTicks / (uint32_t)stepsInBar;
  if (stepTicks == 0) stepTicks = 1;

  for (uint8_t step = 0; step < stepsInBar; step++) {
    uint32_t baseTick32 = (uint32_t)step * stepTicks;
    if (baseTick32 > barTicks) baseTick32 = barTicks;
    uint16_t baseTick = (uint16_t)baseTick32;

    for (uint8_t slot = 0; slot < EMERGENCY_SLOTS; slot++) {
      uint8_t acc = emergencyGet2bit(pid, slot, step, stepsInBar);
      if (acc == 0) continue;
      if (patEventCount >= PAT_MAX_EVENTS) continue;

      uint8_t note = ADP_SLOT_NOTE[slot];
      uint8_t vel  = (acc >= 3 ? 112 : (acc == 2 ? 96 : 64));

      PatternEvent &ev = patEvents[patEventCount++];
      ev.tick   = baseTick;
      ev.status = 0x99;   // ch10 note on
      ev.d1     = note;
      ev.d2     = vel;
    }
  }

  patLoopLenTicks = (uint16_t)barTicks;
  if (patEventCount == 0 || patLoopLenTicks == 0) {
    patLoaded = false;
    return false;
  }

  // BPM timing for pattern preview
  usPerQuarter = 60000000UL / (uint32_t)previewBpm;
  if (usPerQuarter == 0) usPerQuarter = 1;
  usPerTick    = usPerQuarter / (uint32_t)midiPPQ;
  if (usPerTick == 0) usPerTick = 1;

  patLoaded = true;
  return true;
}

void startInternalPatternPlayback(uint8_t pid) {
  stopAllPlaybackAndReset(true);
  if (!loadInternalPatternIntoMemory(pid)) return;

  internalModePlaying = true;
  // Ensure the INTERNAL path starts with the same timing reset semantics as SD patterns.
  beginLoadedPatternPlayback();
}
