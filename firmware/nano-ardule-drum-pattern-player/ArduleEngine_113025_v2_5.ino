// Ardule Playback Engine module - auto-split from main sketch
//
// Contains:
//  - Beat/BPM timing & beat LED control
//  - Pattern playback loop (2-bar absolute-time engine)
//  - SONG (Type 0 MIDI) streaming playback from SD
//
// Relies on global state & helpers declared in the main sketch:
//  - previewBpm, playSource, playState, beatIntervalMs, beatIndex, beatLedPin, beatLedOffAtMs,
//    nextBeatMs, usPerQuarter, usPerTick, midiPPQ, patLoaded, patLoopLenTicks, patLoopStartUs,
//    patEventIndex, patEventCount, patEvents[], previewAllMode, previewLoopCount,
//    playFile, playFileOpen, nextEventUs, haveNextEvent, endOfTrack, runningStatus, etc.
//  - enums/consts: PLAY_SRC_PATTERN, PLAY_SRC_SONG, PLAY_SRC_NONE,
//                  PLAYSTATE_PLAYING, PLAYSTATE_IDLE, PLAYSTATE_PAUSED,
//                  BEATS_PER_BAR, TOTAL_BEATS
//  - helpers: sendMidiMessage2/3, sendMidiPanic, buildCurrentPatternFilePath, buildCurrentSongFilePath,
//             loadCurrentPatternIntoMemory, openCurrentMidiSongFile, readVariableLength, readFileByte,
//             stopBeatEngine(), startBeatEngine(), handleEndOfTrackEvent(), advanceAutoPatternPreview(),
//             updateBeatTimingFromBpm(), showPatternPlayScreen(), showPatternListScreen()
//  - hardware: LED_A0, LED_A1, LED_A2
//

// 패턴 재생 첫 루프 여부 플래그
static bool patFirstTick = true;

// 패턴 재생에서 "직전 플레이 상태"를 기억해서
// PAUSED → PLAYING으로 돌아올 때 루프를 깨끗이 재시작하기 위한 플래그
static PlayState lastPatternPlayState = PLAYSTATE_IDLE;

// Forward declarations (needed in some Arduino build setups when code is split
// across multiple .ino files and auto-prototypes are not generated reliably).
void startBeatEngine();

//////////////////// Pattern start helper ////////////////////
// Both SD-based patterns and INTERNAL (built-in) patterns must start
// with the *exact* same timing/reset semantics, otherwise we can get
// an initial "catch-up" burst and LED misalignment.
void beginLoadedPatternPlayback() {
  // 새 패턴을 시작하므로 Preview All 루프 카운트도 리셋
  previewLoopCount = 0;

  // 패턴 이벤트 인덱스/타이밍 리셋
  patEventIndex  = 0;
  patFirstTick   = true;

  // 패턴 재생 + 비트/LED 엔진 시작
  playSource           = PLAY_SRC_PATTERN;
  playState            = PLAYSTATE_PLAYING;
  lastPatternPlayState = PLAYSTATE_PLAYING;

  startBeatEngine();
}

//////////////////// Beat / BPM ////////////////////

void updateBeatTimingFromBpm() {
  if(previewBpm < 20) previewBpm = 20;

  if (playSource == PLAY_SRC_PATTERN) {
    // 패턴 프리뷰/싱글 재생: previewBpm 기준
    beatIntervalMs = (uint32_t)(60000UL / (uint32_t)previewBpm);
    if (beatIntervalMs == 0) beatIntervalMs = 1;

    usPerQuarter = 60000000UL / (uint32_t)previewBpm;
    if (usPerQuarter == 0) usPerQuarter = 1;
    usPerTick = usPerQuarter / (uint32_t)midiPPQ;
    if (usPerTick == 0) usPerTick = 1;
  } else if (playSource == PLAY_SRC_SONG) {
    // SONG 모드는 MIDI 파일의 템포(usPerQuarter)에 맞추어 LED만 맞춤
    beatIntervalMs = (uint32_t)(usPerQuarter / 1000UL);
    if (beatIntervalMs == 0) beatIntervalMs = 1;
  } else {
    // 기타 경우 (혹시 대비)
    beatIntervalMs = (uint32_t)(60000UL / (uint32_t)previewBpm);
    if (beatIntervalMs == 0) beatIntervalMs = 1;
  }
}

void clearBeatLeds() {
  digitalWrite(LED_A0, LOW);
  digitalWrite(LED_A1, LOW);
  digitalWrite(LED_A2, LOW);
  beatLedPin     = -1;
  beatLedOffAtMs = 0;
}

void startBeatEngine() {
  playState = PLAYSTATE_PLAYING;
  beatIndex = 0;
  updateBeatTimingFromBpm();
  uint32_t now = millis();
  nextBeatMs = now;
  clearBeatLeds();
}

void stopBeatEngine(bool toIdle) {
  if(toIdle) playState = PLAYSTATE_IDLE;
  else       playState = PLAYSTATE_PAUSED;
  clearBeatLeds();
}

void serviceBeatEngine() {
  // Requirement: In SONG mode, LEDs are always OFF.
  if (playSource == PLAY_SRC_SONG) {
    digitalWrite(LED_A0, LOW);
    digitalWrite(LED_A1, LOW);
    digitalWrite(LED_A2, LOW);
    beatLedPin = -1;
    return;
  }

  uint32_t now = millis();

  // 비트 LED 끄기
  if(beatLedPin >= 0 && now >= beatLedOffAtMs) {
    digitalWrite(beatLedPin, LOW);
    beatLedPin = -1;
  }

  if(playState != PLAYSTATE_PLAYING) return;
  if(playSource == PLAY_SRC_SONG)    return; // SONG은 별도(또는 나중에 확장)

  if(now >= nextBeatMs) {
    clearBeatLeds();

    // 패턴 재생 시 비트 표시
    if(beatIndex == 0) {
      digitalWrite(LED_A0, HIGH);   // 루프 시작(1박)
      beatLedPin = LED_A0;
    } else if(beatIndex == BEATS_PER_BAR) {
      digitalWrite(LED_A2, HIGH);   // 2마디의 1박
      beatLedPin = LED_A2;
    } else {
      digitalWrite(LED_A1, HIGH);   // 그 외 박
      beatLedPin = LED_A1;
    }

    uint32_t pulse = beatIntervalMs / 4;
    if(pulse > 80) pulse = 80;
    if(pulse < 20) pulse = 20;
    beatLedOffAtMs = now + pulse;

    beatIndex    = (beatIndex + 1) % TOTAL_BEATS;
    nextBeatMs   = now + beatIntervalMs;
  }
}

//////////////////// MIDI ////////////////////

void sendMidiByte(uint8_t b) {
  MIDI_SERIAL.write(b);
  digitalWrite(LED_TX, HIGH);
  txLedOffAtMs = millis() + 10;
}

void sendMidiMessage3(uint8_t st, uint8_t d1, uint8_t d2) {
  sendMidiByte(st);
  sendMidiByte(d1);
  sendMidiByte(d2);
}

void sendMidiMessage2(uint8_t st, uint8_t d1) {
  sendMidiByte(st);
  sendMidiByte(d1);
}

void sendMidiPanic() {
  for (uint8_t ch = 0; ch < 16; ch++) {
    sendMidiMessage3(0xB0 | ch, 120, 0);
    sendMidiMessage3(0xB0 | ch, 123, 0);
    sendMidiMessage3(0xB0 | ch, 64, 0);
  }
}

//////////////////// Metronome ////////////////////

// Metronome config/state globals are defined in the main sketch.

void recalcMetronomeInterval() {
  // 현재 구현에서는 BPM 클램프만 수행,
  // 실제 인터벌 계산은 processMetronomeClick()에서 매번 수행.
  if (metroBpm < 30) metroBpm = 30;
  if (metroBpm > 250) metroBpm = 250;
}

void setMetronomeConfig(uint16_t bpm, uint8_t beatsPerCycle, bool useAccent) {
  metroBpm           = bpm;
  metroBeatsPerCycle = beatsPerCycle;
  metroAccentEnabled = useAccent;

  for (uint8_t i = 0; i < METRO_SIG_COUNT; i++) {
    if (METRO_SIGS[i] == metroBeatsPerCycle) {
      metroSigIndex = i;
      break;
    }
  }
  recalcMetronomeInterval();
}

void setMetronomeBpm(uint16_t bpm) {
  metroBpm = bpm;
  recalcMetronomeInterval();
}

void setMetronomeBeatsPerCycle(uint8_t beatsPerCycle) {
  metroBeatsPerCycle = beatsPerCycle;
  recalcMetronomeInterval();
}

void setMetronomeAccent(bool useAccent) {
  metroAccentEnabled = useAccent;
}

void startMetronome() {
  recalcMetronomeInterval();
  metroRunning    = true;
  metroBeatIndex  = 0;
  metroNextBeatMs = millis();
}

void stopMetronome() {
  metroRunning = false;
}

bool isMetronomeRunning() {
  return metroRunning;
}

void processMetronomeClick() {
  uint32_t now = millis();
  if (!metroRunning) return;
  if (now < metroNextBeatMs) return;

  bool isAccent = (metroAccentEnabled && (metroBeatIndex == 0));

  uint8_t note = isAccent ? metroAccentNote : metroBeatNote;
  uint8_t vel  = isAccent ? 120 : 90;
  sendMidiMessage3(0x99, note, vel);

  if (isAccent) {
    digitalWrite(LED_A0, HIGH);
    metroAccentOffAtMs = now + 50;
  }

  metroBeatIndex++;
  if (metroBeatIndex >= metroBeatsPerCycle) {
    metroBeatIndex = 0;
  }

  uint32_t intervalMs = (uint32_t)(60000UL / metroBpm);
  if (intervalMs < 60) intervalMs = 60;
  metroNextBeatMs = now + intervalMs;
}

//////////////////// ADS v0.1 (Ardule Data Stream) ////////////////////
// MetaTime principle: events are absolute tick values; BPM/PPQ are header authority.

struct AdsEvent {
  uint32_t tick;   // absolute tick
  uint8_t  status; // MIDI status (may be type-only 0x90/0x80; channel applied from header)
  uint8_t  d1;
  uint8_t  d2;
};

static uint32_t adsStartUs = 0;     // micros() at playback start
static uint32_t adsNextAbsUs = 0;   // next event absolute time (us from start)
static AdsEvent adsNextEv;
static bool     adsHaveNext = false;

static uint16_t readU16LE(File &f) {
  int b0 = readFileByte(f); int b1 = readFileByte(f);
  if (b0 < 0 || b1 < 0) return 0;
  return (uint16_t)((uint16_t)b0 | ((uint16_t)b1 << 8));
}

static uint32_t readU32LE(File &f) {
  uint32_t v = 0;
  for (uint8_t i=0;i<4;i++) {
    int b = readFileByte(f);
    if (b < 0) return 0;
    v |= ((uint32_t)(uint8_t)b) << (8*i);
  }
  return v;
}

static bool readNextAdsEvent() {
  if (!playFileOpen) return false;
  if (adsEventsRead >= adsEventCount) return false;

  uint32_t tick = readU32LE(playFile);
  int st = readFileByte(playFile);
  int d1 = readFileByte(playFile);
  int d2 = readFileByte(playFile);
  int rsv = readFileByte(playFile); // reserved/padding byte (ADS v0.1 uses 8 bytes/event)
  if (st < 0 || d1 < 0 || d2 < 0 || rsv < 0) return false;

  adsNextEv.tick   = tick;
  adsNextEv.status = (uint8_t)st;// Some ADS writers store a compact event type (0..127) instead of a raw MIDI status byte.
// If the high bit is not set, interpret as a simple type code and build a proper MIDI status.
if ((adsNextEv.status & 0x80) == 0) {
  uint8_t t = adsNextEv.status;
  if (t == 0)      adsNextEv.status = (uint8_t)(0x80 | (adsChannel & 0x0F)); // Note Off
  else if (t == 1) adsNextEv.status = (uint8_t)(0x90 | (adsChannel & 0x0F)); // Note On
  else if (t == 2) adsNextEv.status = (uint8_t)(0xB0 | (adsChannel & 0x0F)); // CC
  else if (t == 3) adsNextEv.status = (uint8_t)(0xC0 | (adsChannel & 0x0F)); // Program Change
  else             adsNextEv.status = (uint8_t)(0x90 | (adsChannel & 0x0F)); // Fallback to Note On
}

  adsNextEv.d1     = (uint8_t)d1;
  adsNextEv.d2     = (uint8_t)d2;

  // Apply channel authority if the status byte doesn't include channel nibble.
  if (adsNextEv.status == 0x80 || adsNextEv.status == 0x90) {
    adsNextEv.status = (uint8_t)((adsNextEv.status & 0xF0) | (adsChannel & 0x0F));
  }

  adsNextAbsUs = adsNextEv.tick * usPerTick;
  nextEventUs  = adsStartUs + adsNextAbsUs;
  adsHaveNext  = true;
  adsEventsRead++;
  return true;
}

bool openCurrentAdsSongFile() {
  playFile = SD.open(currentFilePath);
  if (!playFile) return false;
  playFileOpen = true;

  char magic[5] = {0,0,0,0,0};
  for (uint8_t i=0;i<4;i++) {
    int b = readFileByte(playFile);
    if (b < 0) { playFile.close(); playFileOpen=false; return false; }
    magic[i] = (char)b;
  }
  if (strncmp(magic, "ADS0", 4) != 0) {
    playFile.close(); playFileOpen=false; return false;
  }

  adsBpm        = readU16LE(playFile);
  adsPpq        = readU16LE(playFile);
  int ch        = readFileByte(playFile);
    // ADS header channel (0-based 0..15 is recommended by MIDI encoding).
  // Many tools store channel as 0..15 directly. Default to CH10(=9) for drums when missing.
  if (ch < 0) {
    adsChannel = 9;
  } else if (ch <= 15) {
    // Treat as 0-based MIDI channel.
    adsChannel = (uint8_t)ch;
  } else if (ch >= 1 && ch <= 16) {
    // Backward-compat: if someone stored 1..16, convert to 0..15.
    adsChannel = (uint8_t)(ch - 1); // 1-based fallback
  } else {
    adsChannel = 9;                 // safe fallback
  } 
  adsEventCount = readU32LE(playFile);

  if (adsBpm < 20) adsBpm = 20;
  if (adsPpq < 24) adsPpq = 24;

  midiPPQ      = adsPpq;
  usPerQuarter = 60000000UL / (uint32_t)adsBpm;
  if (usPerQuarter == 0) usPerQuarter = 1;
  usPerTick    = usPerQuarter / (uint32_t)midiPPQ;
  if (usPerTick == 0) usPerTick = 1;

  previewBpm = adsBpm; // UI only
  updateBeatTimingFromBpm();

  adsEventsRead = 0;
  adsHaveNext   = false;
  endOfTrack    = false;

  adsStartUs = micros();

  if (!readNextAdsEvent()) {
    endOfTrack = true;
  }
  return true;
}

void serviceAdsPlayback() {
  if (playState != PLAYSTATE_PLAYING) return;
  if (playSource != PLAY_SRC_SONG)    return;
  if (!playFileOpen)                  return;
  if (endOfTrack)                     return;

  uint32_t nowUs = micros();

  if (!adsHaveNext) {
    if (!readNextAdsEvent()) {
      endOfTrack = true;
      handleEndOfTrackEvent();
      return;
    }
  }

  if ((int32_t)(nowUs - nextEventUs) < 0) return;

  uint8_t status = adsNextEv.status;
  uint8_t type   = status & 0xF0;

  if (type == 0x80 || type == 0x90 || type == 0xA0 ||
      type == 0xB0 || type == 0xE0) {
    sendMidiMessage3(status, adsNextEv.d1, adsNextEv.d2);
  } else if (type == 0xC0 || type == 0xD0) {
    sendMidiMessage2(status, adsNextEv.d1);
  }

  adsHaveNext = false;

  if (adsEventsRead >= adsEventCount) {
    endOfTrack = true;
    handleEndOfTrackEvent();
  }
}

//////////////////// 패턴 / SONG 재생 ////////////////////

void startSinglePatternPlayback() {
  if (!sdOK) return;
  if (!buildCurrentPatternFilePath(currentFilePath, sizeof(currentFilePath))) return;
  if (!loadCurrentPatternIntoMemory()) return;

  beginLoadedPatternPlayback();
}

void startAutoPatternPreview() {
  if (!sdOK) return;
  if (genreCount == 0) return;

  uint8_t gidx = currentGenreIndex;
  uint8_t cnt  = genres[gidx].count;
  if (cnt == 0) return;

  if (patListCursor < 0) patListCursor = 0;
  if (patListCursor >= (int16_t)cnt) patListCursor = cnt - 1;

  previewAllMode   = true;
  previewLoopCount = 0;

  uiMode = UIMODE_PAT_SINGLE;

  // 1) 실제 재생을 시작해서 playState를 PLAYSTATE_PLAYING으로 만들고
  startSinglePatternPlayback();

  // 2) 그 상태를 기준으로 화면 갱신
  showPatternPlayScreen();
}

void advanceAutoPatternPreview() {
  if (!previewAllMode) return;

  if (genreCount == 0) {
    previewAllMode   = false;
    previewLoopCount = 0;
    sendMidiPanic();
    playSource = PLAY_SRC_NONE;
    stopBeatEngine(true);
    uiMode = UIMODE_PAT_LIST;
    showPatternListScreen();
    return;
  }

  uint8_t gidx = currentGenreIndex;
  uint8_t cnt  = genres[gidx].count;
  if (cnt == 0) {
    previewAllMode   = false;
    previewLoopCount = 0;
    sendMidiPanic();
    playSource = PLAY_SRC_NONE;
    stopBeatEngine(true);
    uiMode = UIMODE_PAT_LIST;
    showPatternListScreen();
    return;
  }

  int16_t next = patListCursor + 1;
  if (next >= (int16_t)cnt) {
    // 마지막 패턴까지 돌았으면 PREVIEW ALL 종료, 리스트로 복귀
    previewAllMode   = false;
    previewLoopCount = 0;
    sendMidiPanic();
    playSource = PLAY_SRC_NONE;
    stopBeatEngine(true);
    uiMode = UIMODE_PAT_LIST;
    showPatternListScreen();
    return;
  }

  patListCursor     = next;
  previewLoopCount  = 0;

  showPatternPlayScreen();
  startSinglePatternPlayback();
}

void startSongPlayback() {
  if (!sdOK) return;
  if (!buildCurrentSongFilePath(currentFilePath, sizeof(currentFilePath))) return;
  if (currentSongIsADS) {
    if (!openCurrentAdsSongFile()) return;
  } else {
    if (!openCurrentMidiSongFile()) return;
  }

  playSource = PLAY_SRC_SONG;
  // SONG의 playState 변경은 startBeatEngine()에서 담당
  startBeatEngine();
}

void stopAllPlaybackAndReset(bool toIdle) {
  sendMidiPanic();

  if (playFileOpen) {
    playFile.close();
    playFileOpen = false;
  }

  playSource = PLAY_SRC_NONE;
  stopBeatEngine(toIdle);
}

void handleEndOfTrackEvent() {
  if (playSource == PLAY_SRC_PATTERN) {
    // 패턴 루프는 별도로 관리하므로 여기서는 아무것도 안 함
    return;
  } else {
    // SONG 재생 끝
    stopAllPlaybackAndReset(true);
  }
}

void servicePatternPlayback() {
  if (playSource != PLAY_SRC_PATTERN) return;
  if (!patLoaded)                     return;

  // ★ 패턴 재생에서 PAUSE → PLAYING으로 복귀할 때
  //    밀린 이벤트를 한꺼번에 쏟아내지 않고,
  //    새 루프 시작처럼 다루기 위한 처리
  if (lastPatternPlayState == PLAYSTATE_PAUSED &&
      playState            == PLAYSTATE_PLAYING) {
    patFirstTick   = true;
    patEventIndex  = 0;
    previewLoopCount = 0;  // PREVIEW ALL일 때도 깔끔하게 새로 시작
  }
  lastPatternPlayState = playState;

  if (playState != PLAYSTATE_PLAYING) return;

  uint32_t nowUs = micros();

  if (patFirstTick) {
    patLoopStartUs = nowUs;
    patEventIndex  = 0;
    patFirstTick   = false;
  }

  uint32_t loopLenUs = (uint32_t)patLoopLenTicks * usPerTick;
  if (loopLenUs == 0) return;

  // 루프 경계(2마디) 넘었는지 체크
  if ((nowUs - patLoopStartUs) >= loopLenUs) {
    patLoopStartUs += loopLenUs;
    patEventIndex   = 0;

    if (previewAllMode) {
      previewLoopCount++;
      if (previewLoopCount >= PREVIEW_LOOPS_PER_PATTERN) {
        previewLoopCount = 0;
        advanceAutoPatternPreview();
        return;
      }
    }
  }

  // 현재 시각(nowUs)까지 도달한 이벤트를 모두 발사
  uint8_t emitted = 0;
  const uint8_t MAX_EVENTS_PER_SERVICE = 8;
  while (patEventIndex < patEventCount) {
    uint32_t evUs = patLoopStartUs
                  + (uint32_t)patEvents[patEventIndex].tick * usPerTick;

    if (nowUs < evUs) break;


    uint8_t st   = patEvents[patEventIndex].status;
    uint8_t d1   = patEvents[patEventIndex].d1;
    uint8_t d2   = patEvents[patEventIndex].d2;
    uint8_t type = st & 0xF0;

    if (type == 0x80 || type == 0x90 || type == 0xA0 ||
        type == 0xB0 || type == 0xE0) {
      sendMidiMessage3(st, d1, d2);
    } else if (type == 0xC0 || type == 0xD0) {
      sendMidiMessage2(st, d1);
    }

    patEventIndex++;
    emitted++;
    if (emitted >= MAX_EVENTS_PER_SERVICE) break;
  }
}

void serviceSongPlayback() {
  if (currentSongIsADS) { serviceAdsPlayback(); return; }
  if (playState != PLAYSTATE_PLAYING) return;
  if (playSource != PLAY_SRC_SONG)    return;
  if (!playFileOpen)                  return;
  if (endOfTrack)                     return;

  uint32_t nowUs = micros();

  if (!haveNextEvent) {
    uint32_t deltaTicks = readVariableLength(playFile);
    uint32_t deltaUs    = deltaTicks * usPerTick;
    nextEventUs += deltaUs;
    haveNextEvent = true;
  }

  if (nowUs < nextEventUs) return;

  int c = readFileByte(playFile);
  if (c < 0) {
    endOfTrack = true;
    handleEndOfTrackEvent();
    return;
  }

  uint8_t status;
  int     d1 = -1, d2 = -1;

  if (c & 0x80) {
    status = (uint8_t)c;
    if (status == 0xFF) {
      int type = readFileByte(playFile);
      if (type < 0) { endOfTrack = true; handleEndOfTrackEvent(); return; }
      uint32_t len = readVariableLength(playFile);

      if (type == 0x2F) {
        // End of Track
        for (uint32_t i=0; i<len; i++) readFileByte(playFile);
        haveNextEvent = false;
        return;
      } else if (type == 0x51 && len == 3 && playSource == PLAY_SRC_SONG) {
        // Set Tempo
        uint32_t t = 0;
        for (int i=0;i<3;i++) {
          int b = readFileByte(playFile);
          if (b < 0) break;
          t = (t << 8) | (uint8_t)b;
        }
        for (uint32_t i=3; i<len; i++) readFileByte(playFile);

        if (t > 0) {
          usPerQuarter = t;
          usPerTick    = usPerQuarter / (uint32_t)midiPPQ;
          if (usPerTick == 0) usPerTick = 1;
        }
      } else {
        // 기타 Meta 이벤트
        for (uint32_t i=0; i<len; i++) readFileByte(playFile);
      }

      haveNextEvent = false;
      return;
    }
    else if (status == 0xF0 || status == 0xF7) {
      // SysEx 이벤트 건너뛰기
      uint32_t len = readVariableLength(playFile);
      for (uint32_t i=0; i<len; i++) readFileByte(playFile);
      haveNextEvent = false;
      return;
    } else {
      runningStatus = status;
    }
  } else {
    status = runningStatus;
    d1     = c;
  }

  if (status < 0x80) {
    haveNextEvent = false;
    return;
  }

  uint8_t type = status & 0xF0;

  bool need2 = true;
  if (type == 0xC0 || type == 0xD0) need2 = false;

  if (d1 < 0) {
    d1 = readFileByte(playFile);
    if (d1 < 0) { endOfTrack = true; handleEndOfTrackEvent(); return; }
  }
  if (need2) {
    d2 = readFileByte(playFile);
    if (d2 < 0) { endOfTrack = true; handleEndOfTrackEvent(); return; }
  }

  if (type == 0x80 || type == 0x90 || type == 0xA0 ||
      type == 0xB0 || type == 0xE0) {
    if (need2) {
      sendMidiMessage3(status, (uint8_t)d1, (uint8_t)d2);
    }
  } else if (type == 0xC0 || type == 0xD0) {
    sendMidiMessage2(status, (uint8_t)d1);
  }

  haveNextEvent = false;
}