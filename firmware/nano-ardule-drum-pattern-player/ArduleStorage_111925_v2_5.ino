// Ardule Storage / Filesystem module - auto-split from main sketch
//
// Responsibilities:
//  - INDEX.TXT parsing and pattern/genre table loading
//  - SONGS folder scanning and song list loading
//  - Building current pattern/song file paths
//  - ADP (Ardule Drum Pattern) header parsing and pattern loading from SD
//  - Type 0 MIDI song file opening and basic MIDI header parsing
//
// Relies on global state & types defined in the main sketch:
//  - sdOK, patterns[], patternCount, genres[], genreCount, patListCursor, currentGenreIndex
//  - drumSongs[], multiSongs[], drumCount, multiCount, songsRootCursor, songsFileCursor
//  - ADPHeader, patEvents[], patEventCount, patEventIndex, patLoopLenTicks, patLoaded
//  - midiPPQ, previewBpm, currentFilePath, playFile, playFileOpen, runningStatus, usPerQuarter, usPerTick
//  - lcdPrintLines(), sendMidiMessage2/3(), sendMidiPanic(), etc.
//  - SD, File (from <SD.h>)
//

void rebuildGenreOrder();

void trimLineEnding(char *s) {
  int i = 0;
  while(s[i]) {
    if(s[i] == '\r' || s[i] == '\n') {
      s[i] = '\0';
      break;
    }
    i++;
  }
}


void stripFileExtension(char *s) {
  for(int i=0; s[i]; i++) {
    if(s[i] == '.') {
      s[i] = '\0';
      break;
    }
  }
}


void copyTrimmed(char *dst, uint8_t dstSize, const char *src) {
  if(dstSize == 0) return;
  uint8_t i=0;
  for(; i<dstSize-1 && src[i]; i++) {
    dst[i] = src[i];
  }
  dst[i] = '\0';
}

void loadPatternIndexFile() {
  patternCount = 0;   // patterns[]는 이제 쓰지 않으니 0으로 유지
  genreCount   = 0;

  if (!sdOK) return;

  // 1) INDEX.TXT 열기 (/PATTERNS 우선)
  File f = SD.open("/PATTERNS/INDEX.TXT");
  if (!f) {
    // 혹시 옛날 구조를 그대로 쓰고 있다면 /SYSTEM/ 도 한 번 더 시도
    f = SD.open("/SYSTEM/INDEX.TXT");
    if (!f) {
      lcdPrintLines(F("INDEX.TXT ERR  "), F("/PATTERNS or SYSTEM"));
      delay(1000);
      return;
    }
  }

  char buf[128];

  // 2) 헤더부 스킵: "#ID | FILE | ..." 라인까지 건너뜀
  while (f.available()) {
    int len = f.readBytesUntil('\n', buf, sizeof(buf) - 1);
    if (len <= 0) {
      f.close();
      return;
    }
    buf[len] = '\0';
    trimLineEnding(buf);

    if (buf[0] == '#') {
      // "#ID | FILE | GEN | ..." 헤더 라인 찾음
      break;
    }
  }

  // 3) 본문 스캔하며 장르 목록/개수 재구성
  while (f.available()) {
    int len = f.readBytesUntil('\n', buf, sizeof(buf) - 1);
    if (len <= 0) break;

    buf[len] = '\0';
    trimLineEnding(buf);

    if (buf[0] == '\0' || buf[0] == ';' || buf[0] == '#') continue;

    char *p = buf;

    char *tok_id   = strtok(p,   "|");
    char *tok_file = strtok(NULL,"|");
    char *tok_gen  = strtok(NULL,"|");
    // 뒤에 LEN/GRID... 은 지금 안 씀

    if (!tok_id || !tok_file || !tok_gen) continue;

    // 앞 공백 제거
    while (*tok_gen == ' ' || *tok_gen == '\t') tok_gen++;

    // 3-1) 이미 등록된 장르인지 확인
    uint8_t gi;
    for (gi = 0; gi < genreCount; gi++) {
      if (strncmp(tok_gen, genres[gi].gen, GEN_LEN - 1) == 0) {
        break;
      }
    }

    // 3-2) 새로운 장르면 genres[]에 추가
    if (gi == genreCount) {
      if (genreCount >= MAX_GENRES) {
        // 더 이상 장르를 수용할 수 없으면 중단
        break;
      }
      copyTrimmed(genres[genreCount].gen, GEN_LEN, tok_gen);
      genres[genreCount].count = 0;
      gi = genreCount;
      genreCount++;
    }

    // 3-3) 해당 장르의 패턴 개수 증가 (255에서 캡)
    if (genres[gi].count < 255) {
      genres[gi].count++;
    }
  }

  f.close();
  // Default genre order: N↓ (count desc)
  rebuildGenreOrder();
}


// 지정한 장르(gidx)의 n번째 패턴 파일 베이스 이름을 가져온다.
// 예: DRM 장르의 0번째 -> "DRM_P001"
bool getPatternFileBaseByGenreIndex(uint8_t gidx, uint8_t nth,
                                    char *outBase, size_t outSize) {
  if (!sdOK) return false;
  if (gidx >= genreCount) return false;

  File f = SD.open("/PATTERNS/INDEX.TXT");
  if (!f) {
    f = SD.open("/SYSTEM/INDEX.TXT");
    if (!f) return false;  // 둘 다 없으면 실패
  }

  char buf[128];

  // 헤더부를 스킵하고 "#ID | FILE | ..." 라인까지 건너뛴다.
  while (f.available()) {
    int len = f.readBytesUntil('\n', buf, sizeof(buf) - 1);
    if (len <= 0) {
      f.close();
      return false;
    }
    buf[len] = '\0';
    trimLineEnding(buf);
    if (buf[0] == '#') {
      break;
    }
  }

  uint8_t countInGenre = 0;

  // 본문부에서 해당 장르의 nth번째 항목을 찾는다.
  while (f.available()) {
    int len = f.readBytesUntil('\n', buf, sizeof(buf) - 1);
    if (len <= 0) break;

    buf[len] = '\0';
    trimLineEnding(buf);
    if (buf[0] == '\0' || buf[0] == ';' || buf[0] == '#') continue;

    char *p = buf;
    char *tok_id   = strtok(p,   "|");
    char *tok_file = strtok(NULL,"|");
    char *tok_gen  = strtok(NULL,"|");
    // 나머지 필드는 지금은 필요 없음

    if (!tok_id || !tok_file || !tok_gen) continue;

    while (*tok_file == ' ' || *tok_file == '\t') tok_file++;
    while (*tok_gen  == ' ' || *tok_gen  == '\t') tok_gen++;

    // 장르 코드 비교 (예: "DRM")
    if (strncmp(tok_gen, genres[gidx].gen, GEN_LEN - 1) != 0) continue;

    if (countInGenre == nth) {
      stripFileExtension(tok_file);               // ".ADP" 제거
      copyTrimmed(outBase, outSize, tok_file);    // 결과 복사
      f.close();
      return true;
    }
    countInGenre++;
  }

  f.close();
  return false;
}

void loadSongsFromFolder(const char *path, SongInfo *arr, uint8_t &count) {
  count = 0;
  if(!sdOK) return;

  File dir = SD.open(path);
  if(!dir || !dir.isDirectory()) {
    return;
  }

  File entry;
  while( (entry = dir.openNextFile()) ) {
    if(entry.isDirectory()) {
      entry.close();
      continue;
    }
    const char *name = entry.name();
    const char *dot = strrchr(name, '.');
    if(dot) {
      bool isMid = (strcasecmp(dot, ".MID") == 0);
      bool isAds = (strcasecmp(dot, ".ADS") == 0);
      if(isMid || isAds) {
        if(count < MAX_SONGS) {
          char tmp[FILEBASE_LEN];
          strncpy(tmp, name, FILEBASE_LEN-1);
          tmp[FILEBASE_LEN-1] = '\0';
          stripFileExtension(tmp);
          copyTrimmed(arr[count].base, FILEBASE_LEN, tmp);
          arr[count].isAds    = isAds;
          arr[count].typeChar = isAds ? 'a' : 'm';
          count++;
        } else {
          songListFullUntilMs = millis() + 2000;
        }
      }
    }
    entry.close();
  }
  dir.close();
}


bool buildCurrentPatternFilePath(char *outPath, size_t outSize) {
  if (genreCount == 0) return false;
  uint8_t gidx = currentGenreIndex;
  uint8_t cnt  = genres[gidx].count;
  if (cnt == 0) return false;
  if (patListCursor < 0) patListCursor = 0;
  if (patListCursor >= (int16_t)cnt) patListCursor = cnt - 1;

  char base[FILEBASE_LEN];
  if (!getPatternFileBaseByGenreIndex(gidx, (uint8_t)patListCursor,
                                      base, sizeof(base))) {
    return false;
  }

  snprintf(outPath, outSize, "/PATTERNS/%s.ADP", base);
  return true;
}


bool buildCurrentSongFilePath(char *outPath, size_t outSize) {
  SongInfo *arr   = (songsRootCursor == 0) ? drumSongs : multiSongs;
  uint8_t   count = (songsRootCursor == 0) ? drumCount  : multiCount;
  if (count == 0) return false;
  if (songsFileCursor < 0) songsFileCursor = 0;
  if (songsFileCursor >= (int16_t)count) songsFileCursor = count - 1;

  const char *subdir = (songsRootCursor == 0) ? "/SONGS/DRUM/" : "/SONGS/MULTI/";
  snprintf(outPath, outSize, "%s%s.%s", subdir, arr[songsFileCursor].base,
           arr[songsFileCursor].isAds ? "ADS" : "MID");
  currentSongIsADS = arr[songsFileCursor].isAds;
  return true;
}


int readFileByte(File &f) {
  if (!f) return -1;
  return f.read();
}


uint32_t readVariableLength(File &f) {
  uint32_t value = 0;
  while (true) {
    int c = readFileByte(f);
    if (c < 0) return value;
    value = (value << 7) | (c & 0x7F);
    if ((c & 0x80) == 0) break;
  }
  return value;
}
// ---- MIDI/ADS tempo sniff helpers (for SONG UI preview) ----
static uint16_t readU16BE(File &f) {
  int b1 = readFileByte(f);
  int b2 = readFileByte(f);
  if (b1 < 0 || b2 < 0) return 0;
  return (uint16_t)(((uint16_t)b1 << 8) | (uint16_t)b2);
}

static uint32_t readU32BE(File &f) {
  int b1 = readFileByte(f);
  int b2 = readFileByte(f);
  int b3 = readFileByte(f);
  int b4 = readFileByte(f);
  if (b1 < 0 || b2 < 0 || b3 < 0 || b4 < 0) return 0;
  return ((uint32_t)b1 << 24) | ((uint32_t)b2 << 16) | ((uint32_t)b3 << 8) | (uint32_t)b4;
}

static bool sniffAdsBpm(File &f, uint16_t &bpmOut) {
  char magic[4];
  for (uint8_t i = 0; i < 4; i++) {
    int c = readFileByte(f);
    if (c < 0) return false;
    magic[i] = (char)c;
  }
  if (strncmp(magic, "ADS0", 4) != 0) return false;

  // ADS v0.1 header (LE): u16 BPM, u16 PPQ, u8 channel, u32 eventCount
  int lo = readFileByte(f);
  int hi = readFileByte(f);
  if (lo < 0 || hi < 0) return false;
  bpmOut = (uint16_t)((uint16_t)lo | ((uint16_t)hi << 8));
  return true;
}

static bool sniffMidBpm(File &f, uint16_t &bpmOut) {
  // Minimal tempo sniff: find first FF 51 03 tt tt tt within track data.
  char tag[4];
  for (int i = 0; i < 4; i++) { int c = readFileByte(f); if (c < 0) return false; tag[i] = (char)c; }
  if (strncmp(tag, "MThd", 4) != 0) return false;

  uint32_t hlen = readU32BE(f);
  (void)readU16BE(f);         // format
  uint16_t ntrks = readU16BE(f);
  (void)readU16BE(f);         // division

  if (hlen > 6) {
    for (uint32_t k = 0; k < (hlen - 6); k++) { if (readFileByte(f) < 0) break; }
  }

  for (uint16_t t = 0; t < ntrks; t++) {
    for (int i = 0; i < 4; i++) { int c = readFileByte(f); if (c < 0) return false; tag[i] = (char)c; }
    if (strncmp(tag, "MTrk", 4) != 0) return false;

    uint32_t tlen = readU32BE(f);
    uint32_t remain = tlen;

    uint8_t w0 = 0, w1 = 0, w2 = 0;
    while (remain > 0) {
      int c = readFileByte(f);
      if (c < 0) return false;
      remain--;

      w0 = w1; w1 = w2; w2 = (uint8_t)c;

      if (w0 == 0xFF && w1 == 0x51 && w2 == 0x03) {
        if (remain < 3) return false;
        int a = readFileByte(f), b = readFileByte(f), d = readFileByte(f);
        if (a < 0 || b < 0 || d < 0) return false;
        remain -= 3;
        uint32_t usPerQuarter = ((uint32_t)a << 16) | ((uint32_t)b << 8) | (uint32_t)d;
        if (usPerQuarter == 0) return false;
        uint32_t bpm = (60000000UL + usPerQuarter/2) / usPerQuarter;
        bpmOut = (uint16_t)bpm;
        return true;
      }
    }
  }
  return false;
}

bool readSongBpmFromPath(const char *path, bool isAds, uint16_t &bpmOut) {
  if (!sdOK) return false;
  File f = SD.open(path);
  if (!f) return false;

  bool ok = false;
  if (isAds) ok = sniffAdsBpm(f, bpmOut);
  else       ok = sniffMidBpm(f, bpmOut);

  f.close();
  return ok;
}



bool readAdpHeaderAndPayload(File &f, ADPHeader &hdr, uint16_t &payloadLen) {
  payloadLen = 0;

  uint8_t h[20];
  int n = f.read(h, 20);
  if (n != 20) return false;

  hdr.magic[0]  = h[0];
  hdr.magic[1]  = h[1];
  hdr.magic[2]  = h[2];
  hdr.magic[3]  = h[3];
  hdr.version   = h[4];
  hdr.gridCode  = h[5];
  hdr.length    = h[6];
  hdr.slots     = h[7];
  hdr.ppqn      = (uint16_t)h[8] | ((uint16_t)h[9] << 8);
  hdr.swing     = h[10];
  hdr.tempo     = (uint16_t)h[11] | ((uint16_t)h[12] << 8);
  hdr.reserved  = h[13];
  hdr.crc16     = (uint16_t)h[14] | ((uint16_t)h[15] << 8);
  hdr.payloadBytes =
      (uint32_t)h[16] |
      ((uint32_t)h[17] << 8) |
      ((uint32_t)h[18] << 16) |
      ((uint32_t)h[19] << 24);

  if (hdr.magic[0] != 'A' || hdr.magic[1] != 'D' ||
      hdr.magic[2] != 'P' || hdr.magic[3] != '2') {
    return false;
  }
  if (hdr.length == 0 || hdr.length > 48) return false;
  if (hdr.slots == 0 || hdr.slots > 12)   return false;

  int r = f.read(adpPayload, sizeof(adpPayload));
  if (r <= 0) return false;
  payloadLen = (uint16_t)r;
  return true;
}


bool loadCurrentPatternIntoMemory() {
  patEventCount   = 0;
  patEventIndex   = 0;
  patLoopLenTicks = 0;
  patLoaded       = false;

  if (!sdOK) return false;

  File f = SD.open(currentFilePath);
  if (!f) return false;

  ADPHeader hdr;
  uint16_t payloadLen = 0;
  bool ok = readAdpHeaderAndPayload(f, hdr, payloadLen);
  f.close();
  if (!ok) return false;

  uint8_t lengthSteps = hdr.length;
  uint8_t slotsUsed   = hdr.slots;

  uint32_t twoBarTicks = (uint32_t)midiPPQ * 4UL * 2UL;
  if (twoBarTicks > 65535UL) twoBarTicks = 65535UL;
  uint32_t stepTicks = twoBarTicks / (uint32_t)lengthSteps;
  if (stepTicks == 0) stepTicks = 1;

  patEventCount = 0;
  uint16_t pos = 0;

  while (pos < payloadLen) {
    for (uint8_t step = 0; step < lengthSteps; step++) {
      if (pos >= payloadLen) break;

      uint8_t count = adpPayload[pos++];
      uint32_t baseTick32 = (uint32_t)step * stepTicks;
      if (baseTick32 > twoBarTicks) baseTick32 = twoBarTicks;
      uint16_t baseTick = (uint16_t)baseTick32;

      for (uint8_t i = 0; i < count; i++) {
        if (pos >= payloadLen) break;
        uint8_t hit  = adpPayload[pos++];
        uint8_t slot = (hit >> 2) & 0x0F;
        uint8_t acc  = hit & 0x03;

        if (slot >= slotsUsed) continue;
        if (acc == 0) continue;
        if (patEventCount >= PAT_MAX_EVENTS) continue;

        uint8_t note = ADP_SLOT_NOTE[slot];
        uint8_t vel  = (acc >= 3 ? 112 : (acc == 2 ? 96 : 64));

        PatternEvent &ev = patEvents[patEventCount++];

        ev.tick   = baseTick;
        ev.status = 0x99;
        ev.d1     = note;
        ev.d2     = vel;
      }
    }
    break;
  }

  patLoopLenTicks = (uint16_t)twoBarTicks;

  if (patEventCount == 0 || patLoopLenTicks == 0) {
    patLoaded = false;
    return false;
  }

  usPerQuarter = 60000000UL / (uint32_t)previewBpm;
  if (usPerQuarter == 0) usPerQuarter = 1;
  usPerTick    = usPerQuarter / (uint32_t)midiPPQ;
  if (usPerTick == 0) usPerTick = 1;

//  patLoopStartUs = micros();
//  patEventIndex  = 0;

  patLoaded      = true;
  return true;
}


bool openCurrentMidiSongFile() {
  if (playFileOpen) {
    playFile.close();
    playFileOpen = false;
  }

  playFile = SD.open(currentFilePath);
  if (!playFile) return false;

  char id[5] = {0};
  if (playFile.read((uint8_t*)id, 4) != 4 || strncmp(id, "MThd", 4) != 0) {
    playFile.close();
    return false;
  }

  uint8_t hdrLenBuf[4];
  if (playFile.read(hdrLenBuf, 4) != 4) {
    playFile.close();
    return false;
  }
  uint32_t hdrLen = (hdrLenBuf[0]<<24) | (hdrLenBuf[1]<<16) |
                    (hdrLenBuf[2]<<8)  | (hdrLenBuf[3]);

  uint8_t hdr[6];
  if (playFile.read(hdr, 6) != 6) {
    playFile.close();
    return false;
  }

  uint16_t format = (hdr[0]<<8) | hdr[1];
  uint16_t ntrks  = (hdr[2]<<8) | hdr[3];
  uint16_t div    = (hdr[4]<<8) | hdr[5];

  if (hdrLen > 6) {
    uint32_t toSkip = hdrLen - 6;
    while (toSkip-- && playFile.available()) playFile.read();
  }

  if (format > 1 || ntrks == 0) {
    playFile.close();
    return false;
  }

  if (div & 0x8000) {
    playFile.close();
    return false;
  }
  midiPPQ = div;

  if (playFile.read((uint8_t*)id, 4) != 4 || strncmp(id, "MTrk", 4) != 0) {
    playFile.close();
    return false;
  }

  uint8_t lenBuf[4];
  if (playFile.read(lenBuf, 4) != 4) {
    playFile.close();
    return false;
  }

  usPerQuarter = 60000000UL / (uint32_t)previewBpm;
  if (usPerQuarter == 0) usPerQuarter = 1;
  usPerTick = usPerQuarter / (uint32_t)midiPPQ;
  if (usPerTick == 0) usPerTick = 1;

  uint32_t nowUs = micros();
  nextEventUs   = nowUs;
  haveNextEvent = false;
  endOfTrack    = false;
  runningStatus = 0;

  playFileOpen = true;
  return true;
}
