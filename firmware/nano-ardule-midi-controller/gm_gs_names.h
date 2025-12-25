#pragma once
/**
 * gm_gs_names.h — GM/GS Names, Families, DrumKits
 *
 * Usage:
 *   // 한 곳(.ino 파일)에서만:
 *   #define GM_GS_NAMES_IMPL
 *   #include "gm_gs_names.h"
 *
 *   // 나머지 파일에서는:
 *   #include "gm_gs_names.h"
 */

#include <Arduino.h>

// ---------- Families ----------
struct Family { uint8_t startProg; uint8_t endProg; const char* name; };
extern const uint8_t FAMS_COUNT;
extern const Family FAMS[];

void famNameTo(char* out, size_t n, uint8_t famIndex);
uint8_t famClampProg(uint8_t famIndex, int v);

// ---------- GM Program Names (128) ----------
extern const uint8_t GM_COUNT;
extern const char* const GM_NAMES[];
void gmNameTo(char* out, size_t n, uint8_t prog);

// ---------- GS/GM Variation Abbrev ----------
extern const char* const VAR_ABBR[];
void varAbbrTo(char* out, size_t n, uint8_t lsb);

// ---------- Drum Kits ----------
struct DrumKit { uint8_t pc; const char* name; };
extern const uint8_t DKITS_COUNT;
extern const DrumKit DKITS[];
void drumKitNameTo(char* out, size_t n, uint8_t kitIndex);

// ---------- IMPLEMENTATION ----------
#ifdef GM_GS_NAMES_IMPL

// Families
static const char fam_pno[] PROGMEM="Piano";
static const char fam_prc[] PROGMEM="Perc";
static const char fam_org[] PROGMEM="Organ";
static const char fam_gtr[] PROGMEM="Guitar";
static const char fam_bas[] PROGMEM="Bass";
static const char fam_str[] PROGMEM="Strings";
static const char fam_ens[] PROGMEM="Ensemble";
static const char fam_brs[] PROGMEM="Brass";
static const char fam_rds[] PROGMEM="Reeds";
static const char fam_flt[] PROGMEM="Flutes";
static const char fam_led[] PROGMEM="Leads";
static const char fam_pad[] PROGMEM="Pads";
static const char fam_fx [] PROGMEM="FX";
static const char fam_eth[] PROGMEM="Ethnic";
static const char fam_prc2[] PROGMEM="Perc";
static const char fam_fx2[] PROGMEM="FX";

const Family FAMS[] PROGMEM = {
  {  0,  7, fam_pno}, {  8, 15, fam_prc}, { 16, 23, fam_org}, {24, 31, fam_gtr},
  { 32, 39, fam_bas}, { 40, 47, fam_str}, { 48, 55, fam_ens}, {56, 63, fam_brs},
  { 64, 71, fam_rds}, { 72, 79, fam_flt}, { 80, 87, fam_led}, {88, 95, fam_pad},
  { 96,103, fam_fx }, {104,111, fam_eth}, {112,119, fam_prc2}, {120,127, fam_fx2},
};
const uint8_t FAMS_COUNT = sizeof(FAMS)/sizeof(FAMS[0]);

// GM Names (여기서는 일부만 예시, 전체 128개를 이어 붙이시면 됩니다)
static const char n000[] PROGMEM = "Acou Piano";
static const char n001[] PROGMEM = "BrightPno";
static const char n002[] PROGMEM = "ElecGrand";
static const char n003[] PROGMEM = "HonkyTonk";
static const char n004[] PROGMEM = "EPiano 1";
static const char n005[] PROGMEM = "EPiano 2";
static const char n006[] PROGMEM = "Harpsi";
static const char n007[] PROGMEM = "Clavi";
static const char n008[] PROGMEM = "Celesta";
static const char n009[] PROGMEM = "Glocken";
static const char n010[] PROGMEM = "MusicBox";
static const char n011[] PROGMEM = "Vibes";
static const char n012[] PROGMEM = "Marimba";
static const char n013[] PROGMEM = "Xylophone";
static const char n014[] PROGMEM = "TubulBell";
static const char n015[] PROGMEM = "Dulcimer";
static const char n016[] PROGMEM = "DrawbarOr";
static const char n017[] PROGMEM = "PercOrgan";
static const char n018[] PROGMEM = "RockOrgan";
static const char n019[] PROGMEM = "ChurchOrg";
static const char n020[] PROGMEM = "ReedOrgan";
static const char n021[] PROGMEM = "Accordian";
static const char n022[] PROGMEM = "Harmonica";
static const char n023[] PROGMEM = "TangoAccd";
static const char n024[] PROGMEM = "NylonGtr";
static const char n025[] PROGMEM = "SteelGtr";
static const char n026[] PROGMEM = "JazzGtr";
static const char n027[] PROGMEM = "CleanGtr";
static const char n028[] PROGMEM = "MutedGtr";
static const char n029[] PROGMEM = "OverdrGtr";
static const char n030[] PROGMEM = "Dist Gtr";
static const char n031[] PROGMEM = "GtrHarm";
static const char n032[] PROGMEM = "AcouBass";
static const char n033[] PROGMEM = "FngrBass";
static const char n034[] PROGMEM = "PickBass";
static const char n035[] PROGMEM = "Fretless";
static const char n036[] PROGMEM = "SlapBass1";
static const char n037[] PROGMEM = "SlapBass2";
static const char n038[] PROGMEM = "SynBass1";
static const char n039[] PROGMEM = "SynBass2";
static const char n040[] PROGMEM = "Violin";
static const char n041[] PROGMEM = "Viola";
static const char n042[] PROGMEM = "Cello";
static const char n043[] PROGMEM = "ContraB";
static const char n044[] PROGMEM = "Trem Str";
static const char n045[] PROGMEM = "Pizz Str";
static const char n046[] PROGMEM = "Harp";
static const char n047[] PROGMEM = "Timpani";
static const char n048[] PROGMEM = "Str Ens1";
static const char n049[] PROGMEM = "Str Ens2";
static const char n050[] PROGMEM = "SynStr1";
static const char n051[] PROGMEM = "SynStr2";
static const char n052[] PROGMEM = "Choir Aah";
static const char n053[] PROGMEM = "Voice Ooh";
static const char n054[] PROGMEM = "Syn Voice";
static const char n055[] PROGMEM = "Orch Hit";
static const char n056[] PROGMEM = "Trumpet";
static const char n057[] PROGMEM = "Trombone";
static const char n058[] PROGMEM = "Tuba";
static const char n059[] PROGMEM = "MuteTrpt";
static const char n060[] PROGMEM = "FrenchHrn";
static const char n061[] PROGMEM = "BrassSect";
static const char n062[] PROGMEM = "SynBrass1";
static const char n063[] PROGMEM = "SynBrass2";
static const char n064[] PROGMEM = "SopSax";
static const char n065[] PROGMEM = "AltoSax";
static const char n066[] PROGMEM = "TenorSax";
static const char n067[] PROGMEM = "BariSax";
static const char n068[] PROGMEM = "Oboe";
static const char n069[] PROGMEM = "EnglHorn";
static const char n070[] PROGMEM = "Bassoon";
static const char n071[] PROGMEM = "Clarinet";
static const char n072[] PROGMEM = "Piccolo";
static const char n073[] PROGMEM = "Flute";
static const char n074[] PROGMEM = "Recorder";
static const char n075[] PROGMEM = "PanFlute";
static const char n076[] PROGMEM = "Bottle";
static const char n077[] PROGMEM = "Shakuhachi";
static const char n078[] PROGMEM = "Whistle";
static const char n079[] PROGMEM = "Ocarina";
static const char n080[] PROGMEM = "SquareLd";
static const char n081[] PROGMEM = "SawLead";
static const char n082[] PROGMEM = "Calliope";
static const char n083[] PROGMEM = "Chiffer";
static const char n084[] PROGMEM = "Charang";
static const char n085[] PROGMEM = "Solo Vox";
static const char n086[] PROGMEM = "5th Lead";
static const char n087[] PROGMEM = "BassLead";
static const char n088[] PROGMEM = "New Age";
static const char n089[] PROGMEM = "Warm Pad";
static const char n090[] PROGMEM = "Polysynth";
static const char n091[] PROGMEM = "ChoirPad";
static const char n092[] PROGMEM = "BowedPad";
static const char n093[] PROGMEM = "MetalPad";
static const char n094[] PROGMEM = "HaloPad";
static const char n095[] PROGMEM = "SweepPad";
static const char n096[] PROGMEM = "Rain";
static const char n097[] PROGMEM = "SoundTrk";
static const char n098[] PROGMEM = "Crystal";
static const char n099[] PROGMEM = "Atmos";
static const char n100[] PROGMEM = "Bright";
static const char n101[] PROGMEM = "Goblins";
static const char n102[] PROGMEM = "Echoes";
static const char n103[] PROGMEM = "Sci-Fi";
static const char n104[] PROGMEM = "Sitar";
static const char n105[] PROGMEM = "Banjo";
static const char n106[] PROGMEM = "Shamisen";
static const char n107[] PROGMEM = "Koto";
static const char n108[] PROGMEM = "Kalimba";
static const char n109[] PROGMEM = "Bagpipe";
static const char n110[] PROGMEM = "Fiddle";
static const char n111[] PROGMEM = "Shanai";
static const char n112[] PROGMEM = "TinkleBel";
static const char n113[] PROGMEM = "Agogo";
static const char n114[] PROGMEM = "SteelDrms";
static const char n115[] PROGMEM = "Woodblock";
static const char n116[] PROGMEM = "Taiko";
static const char n117[] PROGMEM = "MeloTom";
static const char n118[] PROGMEM = "Syn Drum";
static const char n119[] PROGMEM = "Rev Cym";
static const char n120[] PROGMEM = "FretNoise";
static const char n121[] PROGMEM = "Breath";
static const char n122[] PROGMEM = "Seashore";
static const char n123[] PROGMEM = "Bird";
static const char n124[] PROGMEM = "Telephone";
static const char n125[] PROGMEM = "Helicopt";
static const char n126[] PROGMEM = "Applause";
static const char n127[] PROGMEM = "Gunshot";

const char* const GM_NAMES[] PROGMEM = {
  n000,n001,n002,n003,n004,n005,n006,n007,n008,n009,n010,n011,n012,n013,n014,n015,
  n016,n017,n018,n019,n020,n021,n022,n023,n024,n025,n026,n027,n028,n029,n030,n031,
  n032,n033,n034,n035,n036,n037,n038,n039,n040,n041,n042,n043,n044,n045,n046,n047,
  n048,n049,n050,n051,n052,n053,n054,n055,n056,n057,n058,n059,n060,n061,n062,n063,
  n064,n065,n066,n067,n068,n069,n070,n071,n072,n073,n074,n075,n076,n077,n078,n079,
  n080,n081,n082,n083,n084,n085,n086,n087,n088,n089,n090,n091,n092,n093,n094,n095,
  n096,n097,n098,n099,n100,n101,n102,n103,n104,n105,n106,n107,n108,n109,n110,n111,
  n112,n113,n114,n115,n116,n117,n118,n119,n120,n121,n122,n123,n124,n125,n126,n127
};

const uint8_t GM_COUNT = 128;

// Variation Abbrev
static const char var0[] PROGMEM="Cap";
static const char var1[] PROGMEM="V1";
static const char var2[] PROGMEM="V2";
static const char var3[] PROGMEM="V3";
static const char var4[] PROGMEM="V4";
static const char var5[] PROGMEM="V5";
static const char var6[] PROGMEM="V6";
static const char var7[] PROGMEM="V7";
static const char var8[] PROGMEM="V8";
static const char var9[] PROGMEM="V9";
static const char var10[] PROGMEM="V10";
static const char var11[] PROGMEM="V11";
const char* const VAR_ABBR[] PROGMEM = { var0,var1,var2,var3,var4,var5,var6,var7,var8,var9,var11 };

// Drum Kits
static const char dk_std[] PROGMEM="Standard";
static const char dk_room[] PROGMEM="Room";
static const char dk_power[] PROGMEM="Power";
static const char dk_elec[] PROGMEM="Electronic";
static const char dk_808[] PROGMEM="TR-808";
static const char dk_jazz[] PROGMEM="Jazz";
static const char dk_brsh[] PROGMEM="Brush";
static const char dk_orch[] PROGMEM="Orchestra";
static const char dk_sfx[] PROGMEM="SFX";
static const char dk_cm64[] PROGMEM="CM6432";

const DrumKit DKITS[] PROGMEM = {
  {0, dk_std},{8, dk_room},{16, dk_power},{24, dk_elec},{25, dk_808},
  {32, dk_jazz},{40, dk_brsh},{48, dk_orch},{56, dk_sfx},{127, dk_cm64}
};
const uint8_t DKITS_COUNT = sizeof(DKITS)/sizeof(DKITS[0]);

// ---------- Helpers ----------
static inline void copyProgmemString(char* out, size_t n, const char* p){
  if (!out || n==0) return;
  #if defined(__AVR__)
    uint8_t i=0; char c=0; while (i<n-1 && (c=pgm_read_byte(p++))) out[i++]=c; out[i]=0;
  #else
    strncpy(out, p, n-1); out[n-1]=0;
  #endif
}

void famNameTo(char* out, size_t n, uint8_t famIndex){
  if (!out || n==0){ return; }
  out[0]=0;
  if (famIndex >= FAMS_COUNT) return;
  Family f; memcpy_P(&f, &FAMS[famIndex], sizeof(Family));
  const char* p = (const char*)f.name;
  copyProgmemString(out, n, p);
}

uint8_t famClampProg(uint8_t famIndex, int v){
  Family f; memcpy_P(&f, &FAMS[famIndex], sizeof(Family));
  if (v < f.startProg) v = f.startProg;
  if (v > f.endProg)   v = f.endProg;
  return (uint8_t)v;
}

void gmNameTo(char* out, size_t n, uint8_t prog){
  if (!out || n==0){ return; }
  out[0]=0; if (prog >= GM_COUNT) return;
  const char* p;
  #if defined(__AVR__)
    p = (const char*)pgm_read_ptr(&GM_NAMES[prog]);
  #else
    p = GM_NAMES[prog];
  #endif
  copyProgmemString(out, n, p);
}

void varAbbrTo(char* out, size_t n, uint8_t lsb){
  if (!out || n==0){ return; }
  if (lsb>7) lsb=7;
  const char* p;
  #if defined(__AVR__)
    p = (const char*)pgm_read_ptr(&VAR_ABBR[lsb]);
  #else
    p = VAR_ABBR[lsb];
  #endif
  copyProgmemString(out, n, p);
}

void drumKitNameTo(char* out, size_t n, uint8_t kitIndex){
  if (!out || n==0){ return; }
  out[0]=0; if (kitIndex >= DKITS_COUNT) return;
  DrumKit dk; memcpy_P(&dk, &DKITS[kitIndex], sizeof(DrumKit));
  const char* p = (const char*)dk.name;
  copyProgmemString(out, n, p);
}

#endif // GM_GS_NAMES_IMPL
