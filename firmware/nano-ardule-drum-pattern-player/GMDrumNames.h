#pragma once
#include <Arduino.h>

struct DrumNameEntry {
  uint8_t note;
  char    name8[9];
};

const DrumNameEntry PROGMEM DRUM_NAMES[] = {
  {35, "AcBasDrm"},  // Acoustic Bass Drum
  {36, "BassDrm1"},  // Bass Drum 1
  {37, "SideStck"},  // Side Stick
  {38, "AcSnare "},  // Acoustic Snare
  {39, "HandClap"},  // Hand Clap
  {40, "ElSnare "},  // Electric Snare
  {41, "LoFlrTom"},  // Low Floor Tom
  {42, "ClHiHat "},  // Closed Hi-Hat
  {43, "HiFlrTom"},  // High Floor Tom
  {44, "PedlHHat"},  // Pedal Hi-Hat
  {45, "LowTom1 "},  // Low Tom 1
  {46, "OpnHiHat"},  // Open Hi-Hat
  {47, "LowTom2 "},  // Low Tom 2
  {48, "MidTom  "},  // Mid Tom
  {49, "Crash1  "},  // Crash Cymbal 1
  {50, "HiTom   "},  // High Tom
  {51, "RideCym1"},  // Ride Cymbal 1
  {52, "ChinaCym"},  // Chinese Cymbal
  {53, "RideBell"},  // Ride Bell
  {54, "Tamborin"},  // Tambourine
  {55, "SplashCy"},  // Splash Cymbal
  {56, "Cowbell "},  // Cowbell
  {57, "Crash2  "},  // Crash Cymbal 2
  {58, "VibrSlap"},  // Vibraslap
  {59, "RideCym2"},  // Ride Cymbal 2
  {60, "HiBongo "},  // High Bongo
  {61, "LoBongo "},  // Low Bongo
  {62, "MuteCong"},  // Mute Conga
  {63, "OpenCong"},  // Open Conga
  {64, "HiTumba "},  // High Timbale / Tumba
  {65, "LoTumba "},  // Low Timbale / Tumba
  {66, "HiTimbl "},  // High Timbale
  {67, "LoTimbl "},  // Low Timbale
  {68, "AgogoHi "},  // High Agogo
  {69, "AgogoLo "},  // Low Agogo
  {70, "Cabasa  "},  // Cabasa
  {71, "Maracas "},  // Maracas
  {72, "WhistleL"},  // Whistle Low
  {73, "WhistleH"},  // Whistle High
  {74, "GuiroSt "},  // Guiro Short
  {75, "GuiroLng"},  // Guiro Long
  {76, "Claves  "},  // Claves
  {77, "HiWoodBl"},  // High Wood Block
  {78, "LoWoodBl"},  // Low Wood Block
  {79, "MuteTria"},  // Mute Triangle
  {80, "CuicaHi "},  // High Cuica
  {81, "CuicaLo "}   // Low Cuica
};

const uint8_t DRUM_NAME_COUNT = sizeof(DRUM_NAMES) / sizeof(DRUM_NAMES[0]);

void getDrumName8(uint8_t note, char *out) {
  strcpy(out, "--------");
  for (uint8_t i = 0; i < DRUM_NAME_COUNT; i++) {
    DrumNameEntry e;
    memcpy_P(&e, &DRUM_NAMES[i], sizeof(DrumNameEntry));
    if (e.note == note) {
      strcpy(out, e.name8);
      return;
    }
  }
}


struct DrumKitDef {
  uint8_t pc;
  char    name8[9];
};

const DrumKitDef PROGMEM SAM9703_KITS[] = {
  {  1, "STDSET1 "},
  {  9, "ROOMSET "},
  { 17, "POWERSET"},
  { 25, "ELECSET "},
  { 26, "TR808SET"},
  { 33, "JAZZ    "},
  { 41, "BRUSH   "},
  { 49, "ORCHESTR"},
  { 57, "SFXSET  "},
  {127, "CM6432  "},
};
const uint8_t SAM9703_KITS_COUNT = sizeof(SAM9703_KITS) / sizeof(DrumKitDef);

const DrumKitDef PROGMEM SC8820_KITS[] = {
  {  1, "STANDARD"},
  {  2, "STANDARD"},
  {  3, "STANDARD"},
  {  9, "ROOM    "},
  { 10, "HIPHOP  "},
  { 11, "JUNGLE  "},
  { 12, "TECHNO  "},
  { 13, "ROOMLR  "},
  { 14, "HOUSE   "},
  { 17, "POWER   "},
  { 25, "ELECTRON"},
  { 26, "TR808   "},
  { 27, "DANCE   "},
  { 28, "CR78    "},
  { 29, "TR606   "},
  { 30, "TR707   "},
  { 31, "TR909   "},
  { 33, "JAZZ    "},
  { 34, "JAZZLR  "},
  { 41, "BRUSH   "},
  { 42, "BRUSH2  "},
  { 43, "BRUSH2LR"},
  { 49, "ORCHESTR"},
  { 50, "ETHNIC  "},
  { 51, "KICKSNAR"},
  { 52, "KICKSNAR"},
  { 53, "ASIA    "},
  { 54, "CYMBALCL"},
  { 55, "GAMELAN1"},
  { 56, "GAMELAN2"},
  { 57, "SFX     "},
  { 58, "RHYTHMFX"},
  { 59, "RHYTHMFX"},
  { 60, "RHYTHMFX"},
  { 61, "SFX2    "},
  { 62, "VOICE   "},
  { 63, "CYMCLAP "},
};
const uint8_t SC8820_KITS_COUNT = sizeof(SC8820_KITS) / sizeof(DrumKitDef);
