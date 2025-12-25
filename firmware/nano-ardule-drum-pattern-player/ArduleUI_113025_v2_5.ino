// Ardule UI rendering module - auto-split from main sketch

void lcdPrintLines(const char* l1, const char* l2) {
  lcd.setCursor(0,0);
  for(int i=0;i<LCD_COLS;i++){
    char c = l1[i];
    if(!c){ while(i++<LCD_COLS) lcd.print(' '); break; }
    lcd.print(c);
  }
  lcd.setCursor(0,1);
  for(int i=0;i<LCD_COLS;i++){
    char c = l2[i];
    if(!c){ while(i++<LCD_COLS) lcd.print(' '); break; }
    lcd.print(c);
  }
}

//////////////////// Metronome UI ////////////////////

void showMetronomeScreen() {
  char line1[17];
  char line2[17];

  const char *bpmTag = (metroEditMode == METRO_EDIT_BPM)    ? ">BPM" : " BPM";
  const char *sigTag = (metroEditMode == METRO_EDIT_SIG)    ? ">SIG" : " SIG";
  const char *accTag = (metroEditMode == METRO_EDIT_ACCENT) ? ">ACC" : " ACC";

  snprintf(line1, sizeof(line1), "%s  %s  %s", bpmTag, sigTag, accTag);
  snprintf(line2, sizeof(line2), " %3u   %u/4   %s",
           metroBpm,
           metroBeatsPerCycle,
           metroAccentEnabled ? "ON " : "OFF");

  lcdPrintLines(line1, line2);
}

void updateMetronome() {
  processMetronomeClick();
}

//////////////////// SETTINGS UI ////////////////////

void showSettingsMenuScreen() {
  const char *lineModule = (settingsCursor == 0) ? ">Module Type   " : " Module Type   ";
  const char *lineMetro  = (settingsCursor == 1) ? ">Metronome Snd " : " Metronome Snd ";
  lcdPrintLines(lineModule, lineMetro);
}

void showSettingsModuleScreen() {
  const char *opt0 = (currentModuleType == MODULE_SAM9703) ? ">SAM9703       " : " SAM9703       ";
  const char *opt1 = (currentModuleType == MODULE_SC8820)  ? ">SC-8820      "  : " SC-8820      ";
  lcdPrintLines(opt0, opt1);
}

void showSettingsMetronomeSoundScreen() {
  char line1[17];
  char line2[17];
  char beatName[9];
  char accName[9];

  getDrumName8(metroBeatNote,   beatName);
  getDrumName8(metroAccentNote, accName);

  if (settingsMetroFocus == 0) {
    snprintf(line1, sizeof(line1), ">Bea %2u %-8s", metroBeatNote,   beatName);
    snprintf(line2, sizeof(line2), " Acc %2u %-8s", metroAccentNote, accName);
  } else {
    snprintf(line1, sizeof(line1), " Bea %2u %-8s", metroBeatNote,   beatName);
    snprintf(line2, sizeof(line2), ">Acc %2u %-8s", metroAccentNote, accName);
  }
  lcdPrintLines(line1, line2);
}

// (현재는 별도 내용 없음, 혹시 외부에서 호출할 수 있으니 남겨둠)
void showSettingsScreen() {
  if (uiMode != UIMODE_SETTINGS) return;
}

//////////////////// MAIN MENU ////////////////////

void showMainMenuScreen() {
  int16_t idx = mainCursor;
  if(idx < 0) idx = 0;
  if(idx >= (int16_t)MM_COUNT) idx = MM_COUNT-1;

  const char* items[MM_COUNT] = { "PATTERNS", "SONGS", "METRONOME", "INTERNAL", "SETTINGS" };
  char line1[17], line2[17];

  int16_t next = (idx+1 < (int16_t)MM_COUNT) ? idx+1 : -1;

  // 'MENU >' at columns 0-5, item text from column 7 (가독용)
  snprintf(line1, sizeof(line1), "MENU > %-8s", items[idx]);

  if(next >= 0)
    snprintf(line2, sizeof(line2), "       %-8s", items[next]);
  else
    snprintf(line2, sizeof(line2), "        (end)");

  lcdPrintLines(line1, line2);
}

//////////////////// PATTERN GENRE / LIST ////////////////////

void showPatternGenreScreen() {
  if (genreCount == 0) {
    lcdPrintLines("GENRE> (no data)", "INDEX.TXT empty ");
    return;
  }

  if (patGenreCursor < 0) patGenreCursor = 0;
  if (patGenreCursor >= (int16_t)genreCount) patGenreCursor = genreCount - 1;

  int16_t idx  = patGenreCursor;
  int16_t idx2 = (idx + 1 < (int16_t)genreCount) ? idx + 1 : -1;

  char l1[17], l2[17];

  GenreInfo &g1 = genres[idx];
  snprintf(l1, sizeof(l1), "GENRE> %-3s (%2d)", g1.gen, g1.count);

  if (idx2 >= 0) {
    GenreInfo &g2 = genres[idx2];
    snprintf(l2, sizeof(l2), "       %-3s (%2d)", g2.gen, g2.count);
  } else {
    snprintf(l2, sizeof(l2), "        (end)     ");
  }

  lcdPrintLines(l1, l2);
}

void showPatternListScreen() {
  // 장르/패턴이 하나도 없을 때
  if (genreCount == 0) {
    lcdPrintLines("PTTRN> (no gen)", "INDEX.TXT empty");
    return;
  }

  uint8_t gidx = currentGenreIndex;
  uint8_t cnt  = genres[gidx].count;

  if (cnt == 0) {
    lcdPrintLines("PTTRN> (empty)", "no patterns     ");
    return;
  }

  if (patListCursor < 0) patListCursor = 0;
  if (patListCursor >= (int16_t)cnt) patListCursor = cnt - 1;

  char l1[17], l2[17];
  char base1[FILEBASE_LEN];
  char base2[FILEBASE_LEN];

  bool ok1 = getPatternFileBaseByGenreIndex(
               gidx,
               (uint8_t)patListCursor,
               base1, sizeof(base1));

  bool ok2 = false;
  if (patListCursor + 1 < (int16_t)cnt) {
    ok2 = getPatternFileBaseByGenreIndex(
            gidx,
            (uint8_t)(patListCursor + 1),
            base2, sizeof(base2));
  }

  if (ok1) {
    snprintf(l1, sizeof(l1), "PTTRN> %-8s", base1);
  } else {
    snprintf(l1, sizeof(l1), "PTTRN>  (err)");
  }

  if (ok2) {
    snprintf(l2, sizeof(l2), "       %-8s", base2);
  } else {
    snprintf(l2, sizeof(l2), "        (end)  ");
  }

  lcdPrintLines(l1, l2);
}

//////////////////// PATTERN PLAY (SGL / PREVIEW ALL) ////////////////////

void showPatternPlayScreen() {
  char l1[17];
  char l2[17];

  // LCD 레이아웃 메모:
  // - 각 라인은 16컬럼 (0..15)
  // - 이 화면에서는 0..14까지만 텍스트로 사용하고,
  //   1라인의 15번 컬럼은 아이콘(▶ 또는 ∞) 전용으로 사용

  if (genreCount == 0) {
    lcdPrintLines("P-SGL> (no pat)", "INDEX.TXT empty");
    // 아이콘 자리도 비워 둠
    lcd.setCursor(15, 0);
    lcd.write(' ');
    return;
  }

  uint8_t gidx = currentGenreIndex;
  uint8_t cnt  = genres[gidx].count;

  if (cnt == 0) {
    lcdPrintLines("P-SGL> (empty) ", "no patterns     ");
    lcd.setCursor(15, 0);
    lcd.write(' ');
    return;
  }

  if (patListCursor < 0) patListCursor = 0;
  if (patListCursor >= (int16_t)cnt) patListCursor = cnt - 1;

  char base[FILEBASE_LEN];

  // ----- 1라인 prefix (PLAY>/PAUSE>/READY>) -----
  const char* prefix;
  if (previewAllMode) {
    // 프리뷰 ALL 모드에서는 재생/일시정지만 반영
    if (playState == PLAYSTATE_PAUSED) {
      prefix = "PAUSE>";
    } else {
      // PLAYSTATE_IDLE 와 PLAYSTATE_PLAYING 모두 "PLAY >" 로
      prefix = "PLAY >";
    }
  } else {
    // 단일 패턴 모드
    if (playState == PLAYSTATE_PLAYING) {
      prefix = "PLAY >";
    } else if (playState == PLAYSTATE_PAUSED) {
      prefix = "PAUSE>";
    } else {
      prefix = "READY>";
    }
  }

  if (getPatternFileBaseByGenreIndex(
          gidx,
          (uint8_t)patListCursor,
          base, sizeof(base))) {
    // prefix(6) + 공백 + 파일베이스(최대 8글자) → 0~14까지만 사용
    snprintf(l1, sizeof(l1), "%-6s %-8s", prefix, base);
  } else {
    snprintf(l1, sizeof(l1), "%-6s  (err)", prefix);
  }

  // ----- 2라인: SGL/ALL + 현재 번호/총 개수 + BPM -----
  uint8_t patIdx1 = (uint8_t)patListCursor + 1;

  if (previewAllMode) {
    // 예: "ALL 1/12 BPM120" (15칸 사용, 15번 컬럼은 아이콘용)
    snprintf(l2, sizeof(l2), "ALL%2d/%-2d BPM%3d",
             patIdx1, cnt, previewBpm);
  } else {
    // 예: "SGL 3/12 BPM120"
    snprintf(l2, sizeof(l2), "SGL%2d/%-2d BPM%3d",
             patIdx1, cnt, previewBpm);
  }

  // 두 줄 텍스트 출력 (0~14 칸만 의미 있게 사용)
  lcdPrintLines(l1, l2);

  // ----- 1라인 오른쪽 끝 아이콘(컬럼 15) -----
  lcd.setCursor(15, 0);

  uint8_t iconChar = ' ';   // 기본은 공백

  if (playState == PLAYSTATE_PLAYING) {
    // 재생 중일 때만 아이콘 표시
    if (previewAllMode) {
      // 프리뷰 ALL → ∞
      iconChar = CHAR_INF;   // 사용자 정의 custom char
    } else {
      // 단일 반복 → ▶
      iconChar = CHAR_PLAY;  // 사용자 정의 custom char
    }
  } else {
    // PAUSE/IDLE → 아이콘 지움(공백)
    iconChar = ' ';
  }

  lcd.write(iconChar);
}

//////////////////// SONG PLAY ////////////////////

void showSongPlayScreen() {
  SongInfo *arr   = (songsRootCursor == 0) ? drumSongs : multiSongs;
  uint8_t   count = (songsRootCursor == 0) ? drumCount  : multiCount;

  if (count == 0) {
    lcdPrintLines("SONG > (no song)", "no .MID files   ");
    return;
  }

  if (songsFileCursor < 0) songsFileCursor = 0;
  if (songsFileCursor >= (int16_t)count) songsFileCursor = count - 1;

  const char *base = arr[songsFileCursor].base;

  char l1[17], l2[17];

  const char* prefix;
  if (playState == PLAYSTATE_PLAYING) {
    prefix = "PLAY >";
  } else if (playState == PLAYSTATE_PAUSED) {
    prefix = "PAUSE>";
  } else {
    prefix = "SONG >";
  }

  snprintf(l1, sizeof(l1), "%-6s %-8s", prefix, base);
  snprintf(l2, sizeof(l2), "BPM %4d        ", previewBpm);

  lcdPrintLines(l1, l2);
}

//////////////////// SONGS LIST ////////////////////

void showSongsRootScreen() {
  const char* items[2] = { "DRUM", "MULTI" };
  if(songsRootCursor < 0) songsRootCursor = 0;
  if(songsRootCursor > 1) songsRootCursor = 1;
  int16_t idx = songsRootCursor;
  int16_t idx2 = (idx < 1) ? idx+1 : -1;

  char l1[17], l2[17];
  snprintf(l1, sizeof(l1), "SONGS> %-10s", items[idx]);
  if(idx2 >= 0)
    snprintf(l2, sizeof(l2), "       %-10s", items[idx2]);
  else
    snprintf(l2, sizeof(l2), "        (end)   ");
  lcdPrintLines(l1, l2);
}

void showSongsFileListScreen() {
  SongInfo *arr = (songsRootCursor == 0) ? drumSongs : multiSongs;
  uint8_t count = (songsRootCursor == 0) ? drumCount : multiCount;

  if(count == 0) {
    lcdPrintLines("FILE>  (empty) ", "no .MID files   ");
    return;
  }

  if(songsFileCursor < 0) songsFileCursor = 0;
  if(songsFileCursor >= (int16_t)count) songsFileCursor = count-1;

  int16_t idx  = songsFileCursor;
  int16_t idx2 = (songsFileCursor+1 < (int16_t)count) ? songsFileCursor+1 : -1;

  char l1[17], l2[17];
  snprintf(l1, sizeof(l1), "FILE > %-8s", arr[idx].base);
  if(idx2 >= 0)
    snprintf(l2, sizeof(l2), "       %-8s", arr[idx2].base);
  else
    snprintf(l2, sizeof(l2), "        (end)  ");

  lcdPrintLines(l1, l2);
}

//////////////////// INTERNAL MODE ////////////////////

void showInternalModeScreen() {
  lcdPrintLines("INTERNAL MODE  ", "Built-in Pattern");
}

//////////////////// PARAM MENU (DrumKit / Reverb) ////////////////////

void getCurrentDrumKitInfo(uint8_t &pc, char *name8) {
  DrumKitDef def;
  if (currentModuleType == MODULE_SAM9703) {
    uint8_t count = SAM9703_KITS_COUNT;
    if (count == 0) { pc = 0; strcpy(name8, "--------"); return; }
    if (currentDrumKitIndex < 0) currentDrumKitIndex = 0;
    if (currentDrumKitIndex >= (int16_t)count) currentDrumKitIndex = count - 1;
    memcpy_P(&def, &SAM9703_KITS[currentDrumKitIndex], sizeof(DrumKitDef));
  } else {
    uint8_t count = SC8820_KITS_COUNT;
    if (count == 0) { pc = 0; strcpy(name8, "--------"); return; }
    if (currentDrumKitIndex < 0) currentDrumKitIndex = 0;
    if (currentDrumKitIndex >= (int16_t)count) currentDrumKitIndex = count - 1;
    memcpy_P(&def, &SC8820_KITS[currentDrumKitIndex], sizeof(DrumKitDef));
  }
  pc = def.pc;
  strcpy(name8, def.name8);
}

void applyCurrentDrumKitToModule() {
  uint8_t pc;
  char name8[9];
  getCurrentDrumKitInfo(pc, name8);
  if (pc > 0) {
    uint8_t prg = (pc > 0) ? (pc - 1) : 0;
    sendMidiMessage2(0xC9, prg);
  }
}

void applyCurrentReverbToModule() {
  uint8_t lvl = (reverbLevel > 7) ? 7 : reverbLevel;
  uint8_t val = (uint8_t)(lvl * 16);
  if (val > 127) val = 127;
  sendMidiMessage3(0xB9, 91, val);
}

void showParamMenuScreen() {
  char line1[17];
  char line2[17];
  char kitName[9];
  uint8_t pc = 0;

  getCurrentDrumKitInfo(pc, kitName);

  if (paramFocus == 0) {
    strncpy(line1, ">DrumKit  Reverb", sizeof(line1));
  } else {
    strncpy(line1, " DrumKit >Reverb", sizeof(line1));
  }
  line1[16] = '\0';

  snprintf(line2, sizeof(line2), " %s  Rv%2u", kitName, (unsigned)reverbLevel);
  lcdPrintLines(line1, line2);
}
