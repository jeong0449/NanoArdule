const char BUILD_ID[] PROGMEM = "v250921";

struct DebBtn; struct DebAnalogBtn;
// step_05_routing_layer_split_v1.6b_browser_gsdrums.ino
// Nano Ardule — v1.6 browser with GS Drum Bank auto-select (MSB=121/LSB=0) on CH10
// - Full integration: Browser (Family→Program→Variation), Split/Layer, Volume, Program delay, Part select
// - CH10 drum browser now always sends CC0=121, CC32=0 before Program Change
// Pins follow the user's confirmed mapping (D2/D3 encoder, etc.).

#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#define GM_GS_NAMES_IMPL
#include "gm_gs_names.h"

// ---- Common formatting for line2 (A+B / Split instrument names) ----
#ifndef NAME_A_LEN
#define NAME_A_LEN 7
#define NAME_B_LEN 8
#endif

static inline void makeLine2(char* out16, const char* nmA, const char* nmB){
  char l2[17]; memset(l2,' ',sizeof(l2)); l2[16]=0;
  for (uint8_t i=0;i<NAME_A_LEN && nmA[i];++i){ l2[i]=nmA[i]; }
  l2[NAME_A_LEN]='*';
  for (uint8_t i=0;i<NAME_B_LEN && nmB[i];++i){ l2[NAME_A_LEN+1+i]=nmB[i]; }
  // Copy to out (max 16 chars) and ensure NUL
  strncpy(out16, l2, 16);
  out16[16]=0;
}

// ---------- Config & pins ----------
#define LCD_ADDR        0x27
#define LCD_COLS        16
#define LCD_ROWS        2

#define ENC_A_PIN       2
#define ENC_B_PIN       3
#define ENC_SW_PIN      4
#define ENC_REVERSE     false

#define BTN_SPLIT_PIN   5
#define BTN_STOP_PIN    6
#define BTN_SAVE_PIN    7   // -
#define BTN_LOAD_PIN    8   // +

#define BTN_PART_ANALOG A6
#define PART_THRESH_PRESS   300
#define PART_THRESH_RELEASE 500

#define LED_ACTIVITY    9
#define LED_A_PIN       A0
#define LED_B_PIN       A1
#define LED_DRUM_PIN    A2

#define MIDI_BAUD       31250
#define CH_A            1
#define CH_B            2
#define CH_DRUM         10

#define LCD_REFRESH_MS  200
#define PC_IDLE_MS      200
#define LED_BLINK_MS    5
#define BTN_DEBOUNCE_MS 20
#define PART_LED_BLINK_MS 300

#define BROWSER_BLINK_MS 250
#define SPLIT_BLINK_MS 500
#define OCT_SHIFT_MIN   (-36)
#define OCT_SHIFT_MAX   (+36)

#define REPEAT_START_MS   600
#define REPEAT_INT_SLOW    140
#define REPEAT_INT_MED      90
#define REPEAT_INT_FAST     50

LiquidCrystal_I2C lcd(LCD_ADDR, LCD_COLS, LCD_ROWS);

enum PartMode : uint8_t { MODE_A=0, MODE_B=1, MODE_AB=2, MODE_CH10=3 };
enum UIMode  : uint8_t { UI_VOL=0, UI_PC=1, UI_RVB=2, UI_CHO=3, UI_CUT=4, UI_RES=5, UI_MOD=6, UI_ATK=7, UI_REL=8, UI_BROWSER=9 };
enum EditMode: uint8_t { EDIT_NONE=0, EDIT_SPLIT=1, EDIT_LOCT=2, EDIT_UOCT=3 };

PartMode partMode=MODE_A; UIMode uiMode=UI_VOL; EditMode editMode=EDIT_NONE;
PartMode lastSinglePart = MODE_A;
bool splitOn=false;
bool splitBlinkOn = true;
unsigned long splitBlinkNext = 0;
int8_t lowerOct=0, upperOct=0;
uint8_t splitPoint=60;

struct SplitCfg { bool on; int8_t low; int8_t up; uint8_t point; };
SplitCfg prevSplitCfg={false,0,0,60};

uint8_t progA=0, progB=48;         // A: Piano, B: Strings Ens 1
uint8_t currDrumKitPC = 0; // track currently applied drum kit PC for restore
uint8_t volA=100, volB=100, volD=90;
uint8_t rvbA=40, rvbB=40, rvbD=40;  // Reverb send (CC91)
uint8_t choA=0,  choB=0,  choD=0;   // Chorus send (CC93)

// Added: extra CC caches (Cutoff/Reso/Mod/Attack/Release)
uint8_t cutA=64, cutB=64, cutD=64;   // CC74
uint8_t resA=64, resB=64, resD=64;   // CC71
uint8_t modA=0,  modB=0,  modD=0;    // CC1
uint8_t atkA=64, atkB=64, atkD=64;   // CC73
uint8_t relA=64, relB=64, relD=64;   // CC72

uint8_t bankMSB_A=0, bankLSB_A=0;  // GS melodic: MSB fixed 0
uint8_t bankMSB_B=0, bankLSB_B=0;

bool pcPendingA=false, pcPendingB=false;
unsigned long pcDueA=0, pcDueB=0;

unsigned long nextLcdAt=0; bool dispDirty=true;

// --- Toast message overlay (non-blocking) ---
static unsigned long toastUntilMs = 0;
static char toast1[17] = {0}, toast2[17] = {0};
static inline void showToast(const char* l1, const char* l2, uint16_t ms){
  if (l1){ strncpy(toast1, l1, 16); toast1[16]=0; } else { toast1[0]=0; }
  if (l2){ strncpy(toast2, l2, 16); toast2[16]=0; } else { toast2[0]=0; }
  toastUntilMs = millis() + (unsigned long)ms;
  dispDirty = true;
}

char line1[LCD_COLS+1], line2[LCD_COLS+1];

volatile int8_t enc_delta=0; volatile uint8_t enc_state=0;

struct DebBtn { uint8_t pin; bool stable; bool lastStable; unsigned long tchg; };
DebBtn dbSplit{BTN_SPLIT_PIN, true, true, 0};
DebBtn dbStop {BTN_STOP_PIN,  true, true, 0};
DebBtn dbLoad {BTN_LOAD_PIN,  true, true, 0};
DebBtn dbSave {BTN_SAVE_PIN,  true, true, 0};
DebBtn dbEnc  {ENC_SW_PIN,    true, true, 0};

struct DebAnalogBtn { uint8_t pin; bool stable; bool lastStable; unsigned long tchg; };
DebAnalogBtn dbPart{BTN_PART_ANALOG, true, true, 0};

bool restorePrompt=false, restoreYes=true;
unsigned long ledOffAt=0;
// Blink state for part LEDs during edit modes
bool partBlinkActive=false;
bool partBlinkOn=true;
unsigned long partBlinkNext=0;

struct RepeatState { bool held; unsigned long downAt; unsigned long nextAt; };
RepeatState rptLoad{false,0,0}, rptSave{false,0,0};

// ---------- MIDI helpers ----------
static inline void setLED(){ digitalWrite(LED_ACTIVITY,HIGH); ledOffAt=millis()+LED_BLINK_MS; }
static inline void sendRawCC(uint8_t ch, uint8_t cc, uint8_t val){ Serial.write(0xB0|(uint8_t)(ch-1)); Serial.write(cc); Serial.write(val); setLED(); }
static inline void sendPC(uint8_t ch, uint8_t prg){ Serial.write(0xC0|(uint8_t)(ch-1)); Serial.write(prg&0x7F); setLED(); }
static inline void sendBankAndProgram(uint8_t ch, uint8_t& msbState, uint8_t& lsbState, uint8_t newMSB, uint8_t newLSB, uint8_t program){
  bool needMSB=(newMSB!=msbState), needLSB=(newLSB!=lsbState);
  if (needMSB){ sendRawCC(ch,0,newMSB); msbState=newMSB; }
  /* LSB disabled for SAM9703 */
  sendPC(ch,program);
}

// ---- Safety helper: All-notes/all-sound off across all channels ----
static inline void allNotesOffAllCh(){
  for(uint8_t ch=1; ch<=16; ++ch){
    // Sustain Off, All Notes Off, All Sound Off
    Serial.write(0xB0 | ((ch-1) & 0x0F)); Serial.write(64);  Serial.write(0);
    Serial.write(0xB0 | ((ch-1) & 0x0F)); Serial.write(123); Serial.write(0);
    Serial.write(0xB0 | ((ch-1) & 0x0F)); Serial.write(120); Serial.write(0);
  }
}
// GS drum bank helper (MSB=121/LSB=0 then PC)

// Find drum kit index in DKITS[] by program change (PC) value
static inline uint8_t findKitIndexByPC(uint8_t pc){
  for (uint8_t i=0;i<DKITS_COUNT;i++){
    DrumKit dk; memcpy_P(&dk, &DKITS[i], sizeof(DrumKit));
    if (dk.pc == pc) return i;
  }
  return 0;
}

static inline void setDrumKit(uint8_t kitPC){
  sendRawCC(CH_DRUM, 0, 121);
  sendPC(CH_DRUM, kitPC);
}

// ---------- Encoder ISR ----------
static const int8_t enc_table[16]={0,-1,+1,0,+1,0,0,-1,-1,0,0,+1,0,+1,-1,0};
void enc_isr(){
  uint8_t a=digitalRead(ENC_A_PIN), b=digitalRead(ENC_B_PIN);
  uint8_t curr=(a<<1)|b; uint8_t idx=((enc_state&0x03)<<2)|curr;
  int8_t m=enc_table[idx&0x0F]; enc_state=curr; if(m){ if(ENC_REVERSE)m=-m; enc_delta+=m; }
}

// ---------- Debounce ----------
static bool readBtn(struct DebBtn& d){
  bool raw=digitalRead(d.pin); unsigned long now=millis();
  if (raw!=d.stable){ d.stable=raw; d.tchg=now; }
  if (now-d.tchg>=BTN_DEBOUNCE_MS){
    if (d.stable!=d.lastStable){ d.lastStable=d.stable; if(!d.stable) return true; }
  }
  return false;
}
static bool readPartAnalogPressed(struct DebAnalogBtn& d){
  int val=analogRead(d.pin); bool rawPressed = d.stable ? (val<PART_THRESH_RELEASE) : (val<PART_THRESH_PRESS);
  unsigned long now=millis();
  if (rawPressed!=d.stable){ d.stable=rawPressed; d.tchg=now; }
  if (now-d.tchg>=BTN_DEBOUNCE_MS){
    if (d.stable!=d.lastStable){ d.lastStable=d.stable; if(d.stable) return true; }
  }
  return false;
}

// ---------- Routing core ----------
static inline int clampNote(int v){ if(v<0)return 0; if(v>127)return 127; return v; }
uint8_t runningStatus=0, d1=0; bool haveD1=false;
void sendNote(uint8_t ch, uint8_t note, uint8_t vel, bool on){
  uint8_t st=(on?0x90:0x80)|(uint8_t)(ch-1); Serial.write(st); Serial.write(note); Serial.write(vel); setLED();
}
void routeNote(uint8_t inNote, uint8_t vel, bool on){
  if (splitOn){
    if (inNote<splitPoint){ uint8_t note=(uint8_t)clampNote((int)inNote+lowerOct); sendNote(CH_A,note,vel,on); }
    else { uint8_t note=(uint8_t)clampNote((int)inNote+upperOct); sendNote(CH_B,note,vel,on); }
    return;
  }
  switch(partMode){
    case MODE_A:   sendNote(CH_A,inNote,vel,on); break;
    case MODE_B:   sendNote(CH_B,inNote,vel,on); break;
    case MODE_AB:  sendNote(CH_A,inNote,vel,on); sendNote(CH_B,inNote,vel,on); break;
    case MODE_CH10:sendNote(CH_DRUM,inNote,vel,on); break;
  }
}
void handleMidiByte(uint8_t b){
  if (b>=0xF8){ Serial.write(b); setLED(); return; }
  if (b&0x80){ runningStatus=b; haveD1=false; return; }
  if (!runningStatus) return;
  uint8_t hi=runningStatus&0xF0;
  if (hi==0xC0||hi==0xD0){ Serial.write(runningStatus); Serial.write(b); setLED(); return; }
  if (hi>=0x80&&hi<=0xE0){
    if (!haveD1){ d1=b; haveD1=true; return; }
    uint8_t d2=b; haveD1=false;
    if (hi==0x90||hi==0x80){ bool on=(hi==0x90)&&(d2!=0); routeNote(d1,d2,on); }
    else { Serial.write(runningStatus); Serial.write(d1); Serial.write(d2); setLED(); }
  } else { Serial.write(b); setLED(); }
}

// ---------- Browser model ----------
// Drums (GS typical PC list)
// --- Safe copy of DrumKit name (handles AVR PROGMEM and non-AVR) ---

// --- Safe copy of Family name (handles AVR PROGMEM and non-AVR) ---

struct Browser {
  uint8_t cursor=0;     // 0=Family,1=Program,2=MSB ; on CH10 cursor fixed; on CH10 cursor fixed
  uint8_t famIndex=0;
  uint8_t program=0;
  uint8_t lsb=0;
  uint8_t snapProg=0, snapLSB=0;
  bool    active=false;
  uint8_t kitIndex=0;   // drums
  uint8_t snapKitPC=0;
} browser;

// Abbrev for variation (GS bank LSB 0..7): 0=Cap, 1..7=V1..
// Sanitize to LCD-safe ASCII (replace bytes outside 0x20..0x7E)
static inline void sanitizeAscii(char* s){
  if (!s) return;
  for (uint8_t i=0; s[i]; ++i){ char c=s[i]; if (c<0x20 || c>0x7E) s[i]=' '; }
}

// Convert MIDI note number (0-127) to name like C4 (60=C4)
static inline void noteName(char* out, size_t outSize, uint8_t note){
  static const char* pcs[12] = {"C","C#","D","D#","E","F","F#","G","G#","A","A#","B"};
  uint8_t pc = note % 12; int octave = (int)(note/12) - 1; // 60 -> 5-1=4 => C4
  if (!out || outSize<3) return; // minimal
  snprintf(out, outSize, "%s%d", pcs[pc], octave);
}
// ---------- Helpers ----------
static inline void print16(const char* s){ char b[LCD_COLS+1]; uint8_t n=0; while(s[n]&&n<LCD_COLS){b[n]=s[n];n++;} while(n<LCD_COLS)b[n++]=' '; b[LCD_COLS]=0; lcd.print(b); }
static inline void ledState(){
  // In Split mode, alternate A/B LEDs at SPLIT_BLINK_MS regardless of edit blink
  if (splitOn){
    digitalWrite(LED_A_PIN, splitBlinkOn ? HIGH : LOW);
    digitalWrite(LED_B_PIN, splitBlinkOn ? LOW : HIGH);
    digitalWrite(LED_DRUM_PIN,(partMode==MODE_CH10)?HIGH:LOW);
    return;
  }

  if (partBlinkActive){
    // Blink currently relevant part LED(s) every PART_LED_BLINK_MS
    bool aOn = (partMode==MODE_A || partMode==MODE_AB || splitOn) ? partBlinkOn : false;
    bool bOn = (partMode==MODE_B || partMode==MODE_AB || splitOn) ? partBlinkOn : false;
    bool dOn = (partMode==MODE_CH10) ? partBlinkOn : false;
    digitalWrite(LED_A_PIN, aOn ? HIGH : LOW);
    digitalWrite(LED_B_PIN, bOn ? HIGH : LOW);
    digitalWrite(LED_DRUM_PIN, dOn ? HIGH : LOW);
  } else {
    digitalWrite(LED_A_PIN,(partMode==MODE_A||partMode==MODE_AB||splitOn)?HIGH:LOW);
    digitalWrite(LED_B_PIN,(partMode==MODE_B||partMode==MODE_AB||splitOn)?HIGH:LOW);
    digitalWrite(LED_DRUM_PIN,(partMode==MODE_CH10)?HIGH:LOW);
  }
}
static inline void famName(uint8_t idx, char* buf, uint8_t buflen){
  Family f; memcpy_P(&f,&FAMS[idx],sizeof(Family));
  const char* p=(const char*)pgm_read_word(&f.name);
  uint8_t i=0; char c; while(i<buflen-1 && (c=pgm_read_byte(p++))) buf[i++]=c; buf[i]=0;
}

// ---------- UI rendering ----------
void renderLCD(){
  unsigned long now=millis(); if (now<nextLcdAt && !dispDirty) return; nextLcdAt=now+LCD_REFRESH_MS; dispDirty=false;

  // Toast overlay takes precedence
  if (toastUntilMs){
    long remain = (long)(toastUntilMs - now);
    if (remain > 0){
      lcd.setCursor(0,0); print16(toast1);
      lcd.setCursor(0,1); print16(toast2[0] ? toast2 : "                ");
      return;
    } else {
      toastUntilMs = 0;
      // fall through to normal rendering
    }
  }
if (uiMode==UI_BROWSER){
    if (partMode==MODE_CH10){
      DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
      char kitName[12]; drumKitNameTo(kitName, sizeof(kitName), browser.kitIndex);
      snprintf(line1,sizeof(line1),"DRUM KIT  PC:%3u", dk.pc);
      snprintf(line2,sizeof(line2),"%-12s  \x7E  ", kitName);
      lcd.setCursor(0,0); print16(line1);
      lcd.setCursor(0,1); print16(line2);
      return;
    }
    char fam[12]; famNameTo(fam, sizeof(fam), browser.famIndex); sanitizeAscii(fam);
    char nm[8];  gmNameTo(nm, sizeof(nm), browser.program); sanitizeAscii(nm);
    char vnm[4]; varAbbrTo(vnm, sizeof(vnm), browser.lsb);
    char f6[7]; strncpy(f6, fam, 6); f6[6]=0; // compact to 6 chars
    char n6[7]; strncpy(n6, nm, 6); n6[6]=0;
    char c0 = (browser.cursor==0)?'*':' ';
    char c1 = (browser.cursor==1)?'*':' ';
    char c2 = (browser.cursor==2)?'*':' ';
    // Line1: "*F:Piano  Pno1  " (F: fam6, second column: prog short name)
    snprintf(line1,sizeof(line1),"%cF:%-6s %-6s", c0, f6, n6);
    // Line2: "*P:  40  *V:Cap" (compact, shows var abbr)
    snprintf(line2,sizeof(line2),"%cP:%3u  %cMSB:%3u", c1, browser.program, c2, browser.lsb);
    lcd.setCursor(0,0); print16(line1);
    lcd.setCursor(0,1); print16(line2);
    return;
  }
  
  // --- Split EDIT screen overrides the default multi-channel view ---
  if (splitOn && editMode!=EDIT_NONE){
    const char* tag=(editMode==EDIT_SPLIT)?"Sp":(editMode==EDIT_LOCT)?"Lo":"Up";
    char nn[6]; noteName(nn, sizeof(nn), splitPoint); snprintf(line1,sizeof(line1),"Split[%s] %s", tag, nn);
    int8_t lo = lowerOct/12, up = upperOct/12;
    char l2[17]; snprintf(l2, sizeof(l2), "Lo:%+2d  Up:%+2d", (int)lo, (int)up);
    lcd.setCursor(0,0); print16(line1);
    lcd.setCursor(0,1); print16(l2);
    return;
  }
// === Unified early override for MULTI-CHANNEL (Split or A+B Layer) ===
  if (splitOn || partMode==MODE_AB){
    const bool isSplit = splitOn;
    // Line1: "A/B VOL: %3u/%3u" or "A+B VOL: %3u+%3u"
    if (isSplit){
      snprintf(line1, sizeof(line1), "A/B VOL: %3u/%3u", (unsigned)volA, (unsigned)volB);
    } else {
      snprintf(line1, sizeof(line1), "A+B VOL: %3u+%3u", (unsigned)volA, (unsigned)volB);
    }
    // Line2: names 7 + space + 8
    char nmA[24], nmB[24];
    gmNameTo(nmA, sizeof(nmA), progA);
    gmNameTo(nmB, sizeof(nmB), progB);
      makeLine2(line2, nmA, nmB);
    lcd.setCursor(0,0); print16(line1);
    lcd.setCursor(0,1); print16(line2);
    return;
  }

  // === Injected: Preferred displays for SPLIT and A+B ===
  // SPLIT: two-line display "A/B VOL:  98/100" and names 7 + space + 8
  if (splitOn){
    char vA[4]; snprintf(vA,sizeof(vA), "%u", volA);
    char vB[4]; snprintf(vB,sizeof(vB), "%u", volB);
    char abStr[8]; snprintf(abStr, sizeof(abStr), "%s/%s", vA, vB);
    const char* prefix = "A/B VOL:"; uint8_t baseLen = 8;
    uint8_t lenAB = (uint8_t)strlen(abStr);
    uint8_t spaces = (baseLen + 2 + lenAB) <= 16 ? 2 : 1;
    memset(line1,
' ',sizeof(line1)); line1[0]=0;
    strncpy(line1, prefix, sizeof(line1)-1);
    uint8_t curLen = (uint8_t)strlen(line1);
    while (spaces-- && curLen < sizeof(line1)-1){ line1[curLen++]=' '; line1[curLen]=0; }
    if (curLen + lenAB <= 16){
      while (curLen < 16 - lenAB && curLen < sizeof(line1)-1){ line1[curLen++]=' '; line1[curLen]=0; }
      strncat(line1, abStr, sizeof(line1)-strlen(line1)-1);
    } else {
      strncat(line1, abStr, sizeof(line1)-strlen(line1)-1);
    }
    char nmA[24], nmB[24];
    gmNameTo(nmA, sizeof(nmA), progA);
    gmNameTo(nmB, sizeof(nmB), progB);
      makeLine2(line2, nmA, nmB);
    lcd.setCursor(0,0); print16(line1);
    lcd.setCursor(0,1); print16(line2);
    return;
  }
  // A+B: two-line display "A+B VOL:  98/100" and names 7 + space + 8
  if (partMode==MODE_AB){
    char vA[4]; snprintf(vA,sizeof(vA), "%u", volA);
    char vB[4]; snprintf(vB,sizeof(vB), "%u", volB);
    char abStr[8]; snprintf(abStr, sizeof(abStr), "%s/%s", vA, vB);
    const char* prefix = "A+B VOL:"; uint8_t baseLen = 8;
    uint8_t lenAB = (uint8_t)strlen(abStr);
    uint8_t spaces = (baseLen + 2 + lenAB) <= 16 ? 2 : 1;
    memset(line1,' ',sizeof(line1)); line1[0]=0;
    strncpy(line1, prefix, sizeof(line1)-1);
    uint8_t curLen = (uint8_t)strlen(line1);
    while (spaces-- && curLen < sizeof(line1)-1){ line1[curLen++]=' '; line1[curLen]=0; }
    if (curLen + lenAB <= 16){
      while (curLen < 16 - lenAB && curLen < sizeof(line1)-1){ line1[curLen++]=' '; line1[curLen]=0; }
      strncat(line1, abStr, sizeof(line1)-strlen(line1)-1);
    } else {
      strncat(line1, abStr, sizeof(line1)-strlen(line1)-1);
    }
    char nmA[24], nmB[24];
    gmNameTo(nmA, sizeof(nmA), progA);
    gmNameTo(nmB, sizeof(nmB), progB);
      makeLine2(line2, nmA, nmB);
    lcd.setCursor(0,0); print16(line1);
    lcd.setCursor(0,1); print16(line2);
    return;
  }

  if (splitOn){
    const char* tag=(editMode==EDIT_SPLIT)?"Sp":(editMode==EDIT_LOCT)?"Lo":(editMode==EDIT_UOCT)?"Up":"  ";
    snprintf(line1,sizeof(line1),"Split[%s] P:%3u",tag,splitPoint);
  } else {
    bool suppressAppend=false;
    
    // === Custom A+B display for VOL mode ===
    if (partMode==MODE_AB && uiMode==UI_VOL){
      // Line1: "A+B VOL:  98/100" (fixed width %3u/%3u)
      snprintf(line1, sizeof(line1), "A+B VOL: %3u+%3u", (unsigned)volA, (unsigned)volB);
      // Line2: instrument names only, 7 chars + space + 8 chars (trim/pad)
      char nmA[24], nmB[24];
      gmNameTo(nmA, sizeof(nmA), progA);
      gmNameTo(nmB, sizeof(nmB), progB);
      makeLine2(line2, nmA, nmB);
      lcd.setCursor(0,0); print16(line1);
      lcd.setCursor(0,1); print16(line2);
      return;
    // === Custom SPLIT (A/B) display for VOL mode ===
    if (splitOn && uiMode==UI_VOL){
      // Line1: "A/B VOL:  98/100" (fixed width %3u/%3u)
    snprintf(line1, sizeof(line1), "A/B VOL: %3u/%3u", (unsigned)volA, (unsigned)volB);
    // Line2: instrument names only, 7 + space + 8
      char nmA[24], nmB[24];
      gmNameTo(nmA, sizeof(nmA), progA);
      gmNameTo(nmB, sizeof(nmB), progB);
      makeLine2(line2, nmA, nmB);
      lcd.setCursor(0,0); print16(line1);
      lcd.setCursor(0,1); print16(line2);
      return;
    }

    }
const char* m=(partMode==MODE_A)?"A":(partMode==MODE_B)?"B":(partMode==MODE_AB)?"A+B":"DRM";
    
    // Custom single-channel line1 formats (no leading zeros in values)
    if (!splitOn && partMode!=MODE_AB){
      char part3[4];
      if (partMode==MODE_A) { strcpy(part3,"A  "); }
      else if (partMode==MODE_B) { strcpy(part3,"B  "); }
      else { strcpy(part3,"DRM"); }

      if (uiMode==UI_VOL){
        // Format: PART(3)+space(1)+"VOLUME"(6)+space(3)+value(0-127)
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?volA:(partMode==MODE_B?volB:volD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "VOLUME", num);
        // suppressAppend disabled to allow right-append of value
      } else if (uiMode==UI_RVB){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?rvbA:(partMode==MODE_B?rvbB:rvbD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "REVERB", num);
        // suppressAppend disabled to allow right-append of value
      } else if (uiMode==UI_CHO){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?choA:(partMode==MODE_B?choB:choD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "CHORUS", num);
        // suppressAppend disabled to allow right-append of value
      }
      else if (uiMode==UI_CUT){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?cutA:(partMode==MODE_B?cutB:cutD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "CUTOFF", num);
      } else if (uiMode==UI_RES){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?resA:(partMode==MODE_B?resB:resD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "RESON", num);
      } else if (uiMode==UI_MOD){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?modA:(partMode==MODE_B?modB:modD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "MOD", num);
      } else if (uiMode==UI_ATK){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?atkA:(partMode==MODE_B?atkB:atkD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "ATTACK", num);
      } else if (uiMode==UI_REL){
        char num[4]; snprintf(num, sizeof(num), "%u", (partMode==MODE_A?relA:(partMode==MODE_B?relB:relD)));
        snprintf(line1, sizeof(line1), "%-3s %-6s   %-3s", part3, "RELEASE", num);
      }
    
    }
if (uiMode==UI_PC && partMode!=MODE_AB) snprintf(line1,sizeof(line1),"%-5sPRG CHG",m);
    else {
      const char* md =
        (uiMode==UI_PC) ? "PC" :
        (uiMode==UI_RVB) ? "REVERB" :
        (uiMode==UI_CHO) ? "CHORUS" :
        (uiMode==UI_CUT) ? "CUTOFF" :
        (uiMode==UI_RES) ? "RESON" :
        (uiMode==UI_MOD) ? "MOD" :
        (uiMode==UI_ATK) ? "ATTACK" :
        (uiMode==UI_REL) ? "RELEASE" : "VOLUME";
      snprintf(line1, sizeof(line1), "%-4s %-6s", m, md);
    }
  if (!suppressAppend) { // -
// Append right-aligned values based on mode ---
  {
    char valStr[14] = "";
    // Single-channel (not split/layer) => show pure number at FAR RIGHT
    if (!splitOn && partMode!=MODE_AB){
      if (uiMode==UI_VOL){
        uint8_t v = (partMode==MODE_A?volA:(partMode==MODE_B?volB:volD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_RVB){
        uint8_t v = (partMode==MODE_A?rvbA:(partMode==MODE_B?rvbB:rvbD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_CHO){
        uint8_t v = (partMode==MODE_A?choA:(partMode==MODE_B?choB:choD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_PC){
        if (partMode==MODE_CH10){
          DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
          snprintf(valStr, sizeof(valStr), "%u", dk.pc);
        } else {
          uint8_t v = (partMode==MODE_A?progA:progB);
          snprintf(valStr, sizeof(valStr), "%u", v);
        }
      } else if (uiMode==UI_CUT){
        uint8_t v = (partMode==MODE_A?cutA:(partMode==MODE_B?cutB:cutD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_RES){
        uint8_t v = (partMode==MODE_A?resA:(partMode==MODE_B?resB:resD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_MOD){
        uint8_t v = (partMode==MODE_A?modA:(partMode==MODE_B?modB:modD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_ATK){
        uint8_t v = (partMode==MODE_A?atkA:(partMode==MODE_B?atkB:atkD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_REL){
        uint8_t v = (partMode==MODE_A?relA:(partMode==MODE_B?relB:relD));
        snprintf(valStr, sizeof(valStr), "%u", v);

        if (partMode==MODE_CH10){
          DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
          snprintf(valStr, sizeof(valStr), "%u", dk.pc);
        } else {
          uint8_t v = (partMode==MODE_A?progA:progB);
          snprintf(valStr, sizeof(valStr), "%u", v);
        }
      }
    } else {
      // Multi-channel or split: keep the previous prefixed format
      if (uiMode==UI_VOL){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "VV:%3u/%3u", volA, volB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "VV:%3u", volA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "VV:%3u", volB);
        else snprintf(valStr, sizeof(valStr), "VV:%3u", volD);
      } else if (uiMode==UI_PC){
        if (partMode==MODE_CH10){
          DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
          snprintf(valStr, sizeof(valStr), "%u", dk.pc);
        } else {
          uint8_t v = (partMode==MODE_A?progA:progB);
          snprintf(valStr, sizeof(valStr), "%u", v);
        }
      } else if (uiMode==UI_CUT){
        uint8_t v = (partMode==MODE_A?cutA:(partMode==MODE_B?cutB:cutD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_RES){
        uint8_t v = (partMode==MODE_A?resA:(partMode==MODE_B?resB:resD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_MOD){
        uint8_t v = (partMode==MODE_A?modA:(partMode==MODE_B?modB:modD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_ATK){
        uint8_t v = (partMode==MODE_A?atkA:(partMode==MODE_B?atkB:atkD));
        snprintf(valStr, sizeof(valStr), "%u", v);
      } else if (uiMode==UI_REL){
        uint8_t v = (partMode==MODE_A?relA:(partMode==MODE_B?relB:relD));
        snprintf(valStr, sizeof(valStr), "%u", v);

        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "PV:%3u/%3u", progA, progB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "PV:%3u", progA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "PV:%3u", progB);
        else { DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit)); snprintf(valStr, sizeof(valStr), "PV:%3u", dk.pc); }
      } else if (uiMode==UI_RVB){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "RV:%3u/%3u", rvbA, rvbB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "RV:%3u", rvbA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "RV:%3u", rvbB);
        else snprintf(valStr, sizeof(valStr), "RV:%3u", rvbD);
      
      } else if (uiMode==UI_CHO){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "CV:%3u/%3u", choA, choB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "CV:%3u", choA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "CV:%3u", choB);
        else snprintf(valStr, sizeof(valStr), "CV:%3u", choD);
      } else if (uiMode==UI_CUT){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "CT:%3u/%3u", cutA, cutB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "CT:%3u", cutA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "CT:%3u", cutB);
        else snprintf(valStr, sizeof(valStr), "CT:%3u", cutD);
      } else if (uiMode==UI_RES){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "RS:%3u/%3u", resA, resB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "RS:%3u", resA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "RS:%3u", resB);
        else snprintf(valStr, sizeof(valStr), "RS:%3u", resD);
      } else if (uiMode==UI_MOD){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "MD:%3u/%3u", modA, modB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "MD:%3u", modA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "MD:%3u", modB);
        else snprintf(valStr, sizeof(valStr), "MD:%3u", modD);
      } else if (uiMode==UI_ATK){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "AT:%3u/%3u", atkA, atkB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "AT:%3u", atkA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "AT:%3u", atkB);
        else snprintf(valStr, sizeof(valStr), "AT:%3u", atkD);
      } else if (uiMode==UI_REL){
        if (partMode==MODE_AB) snprintf(valStr, sizeof(valStr), "RL:%3u/%3u", relA, relB);
        else if (partMode==MODE_A) snprintf(valStr, sizeof(valStr), "RL:%3u", relA);
        else if (partMode==MODE_B) snprintf(valStr, sizeof(valStr), "RL:%3u", relB);
        else snprintf(valStr, sizeof(valStr), "RL:%3u", relD);
      }}

    // Right-align valStr at end of line1
    uint8_t L=(uint8_t)strlen(valStr);
    if (L<LCD_COLS && L>0){
      uint8_t startCol=LCD_COLS-L;
      uint8_t curLen=(uint8_t)strlen(line1);
      while(curLen<startCol && curLen<sizeof(line1)-1){ line1[curLen++]=' '; line1[curLen]=0; }
      if (startCol<sizeof(line1)-1){ strncpy(&line1[startCol], valStr, sizeof(line1)-startCol-1); line1[sizeof(line1)-1]=0; }
    }
  }
}

  char name[12];
  if (splitOn){
    char na[8], nb[8];
    gmNameTo(name, sizeof(name), progA); strncpy(na,name,7); na[7]=0;
    gmNameTo(name, sizeof(name), progB); strncpy(nb,name,7); nb[7]=0;
    snprintf(line2,sizeof(line2),"A:%-7sB:%-7s",na,nb);
  } else if (partMode==MODE_AB){
    gmNameTo(name, sizeof(name), progA); char na[6]; strncpy(na,name,5); na[5]=0;
    gmNameTo(name, sizeof(name), progB); char nb[6]; strncpy(nb,name,5); nb[5]=0;
    snprintf(line2,sizeof(line2),"A:%-7sB:%-7s",na,nb);
  } else if (partMode==MODE_A){
    gmNameTo(name, sizeof(name), progA); char name10[11]; strncpy(name10,name,10); name10[10]=0;
    if (uiMode==UI_PC) snprintf(line2,sizeof(line2),"1:%-10s %03u",name10,progA);
    else snprintf(line2,sizeof(line2),"1:%-10s", name10);
  } else if (partMode==MODE_B){
    gmNameTo(name, sizeof(name), progB); char name10[11]; strncpy(name10,name,10); name10[10]=0;
    if (uiMode==UI_PC) snprintf(line2,sizeof(line2),"2:%-10s %03u",name10,progB);
    else snprintf(line2,sizeof(line2),"2:%-10s", name10);
    } else {
    DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
    char kitName[12]; drumKitNameTo(kitName, sizeof(kitName), browser.kitIndex);
    if (uiMode==UI_PC) snprintf(line2,sizeof(line2),"10:%-9s %03u", kitName, dk.pc);
    else snprintf(line2,sizeof(line2),"10:%-13s", kitName);
  }
  lcd.setCursor(0,0); print16(line1);
  lcd.setCursor(0,1); print16(line2);
}
}

// ---------- Apply browser selection ----------
void applyBrowser(){
  if (partMode==MODE_CH10){
    DrumKit dk; memcpy_P(&dk,&DKITS[browser.kitIndex],sizeof(DrumKit));
    setDrumKit(dk.pc);
    currDrumKitPC = dk.pc;
    return;
  }
  // Tone (A/B): MSB = browser.msb (using browser.lsb var), LSB fixed 0, Program=browser.program
  if (partMode==MODE_A){
    bankMSB_A=browser.lsb; bankLSB_A=0; progA=browser.program;
    pcPendingA=true; pcDueA=millis()+PC_IDLE_MS;
  } else if (partMode==MODE_B){
    bankMSB_B=browser.lsb; bankLSB_B=0; progB=browser.program;
    pcPendingB=true; pcDueB=millis()+PC_IDLE_MS;
  }
}

// Preview send for browser (tone parts) without committing globals
static inline void previewBrowserTone(){
  uint8_t ch = (partMode==MODE_A)? CH_A : CH_B;
  sendRawCC(ch, 0, browser.lsb);
  sendPC(ch, browser.program);
}

// ---------- Input handlers ----------
void enterBrowser(){

  // Browser mode LED blink at 0.25s
  partBlinkActive = true; partBlinkOn = true; partBlinkNext = millis() + BROWSER_BLINK_MS; ledState();
// Guard: allow browser only in A, B, or CH10 (DRUM) single modes
  if (splitOn || partMode==MODE_AB){
    showToast("BROWSER A/B/DRUM", "ONLY", 900);
    return;
  }
  uiMode=UI_BROWSER; browser.cursor=0; lcd.clear();
  if (partMode==MODE_CH10){ browser.kitIndex=findKitIndexByPC(currDrumKitPC); browser.snapKitPC = currDrumKitPC; }
  else if (partMode==MODE_A){ browser.program=progA; browser.lsb=bankMSB_A; }
  else { browser.program=progB; browser.lsb=bankMSB_B; }
  browser.famIndex=0; for (uint8_t i=0;i<FAMS_COUNT;i++){
    Family f; memcpy_P(&f,&FAMS[i],sizeof(Family));
    if (browser.program>=f.startProg && browser.program<=f.endProg){ browser.famIndex=i; break; }
  }
  browser.snapProg=browser.program; browser.snapLSB=browser.lsb;
  dispDirty=true;
}
void exitBrowser(bool apply){
  if (apply){
    if (partMode==MODE_CH10 || browser.program!=browser.snapProg || browser.lsb!=browser.snapLSB){
      applyBrowser();
    }
  } else {
    // Revert to snapped sound
    if (partMode==MODE_CH10){
      setDrumKit(browser.snapKitPC);
    } else {
      uint8_t ch = (partMode==MODE_A)? CH_A : CH_B;
      sendRawCC(ch, 0, browser.snapLSB);
      sendPC(ch, browser.snapProg);
    }
  }
  // Leave browser and stop its blink (loop() will also sync)
  if (uiMode==UI_BROWSER) uiMode=UI_VOL;
  partBlinkActive = (splitOn && editMode!=EDIT_NONE); // typical edit blink state
  dispDirty=true;
}

void handleEncoderBtn(){
  if (partMode==MODE_AB && !splitOn){ if (digitalRead(ENC_SW_PIN)==LOW){} return; }

  // FSM: Long-press to enter/exit Browser; short press cycles fields
  static bool pressed=false;
  static bool longFired=false;
  static unsigned long downAt=0;

  bool isDown = (digitalRead(ENC_SW_PIN)==LOW);

  if (isDown){
    if (!pressed){ pressed=true; longFired=false; downAt=millis(); }
    if (!longFired && (millis()-downAt > 700)){
      longFired=true;
      if (uiMode==UI_BROWSER){
        exitBrowser(true); // save and exit
      } else if (!splitOn && (partMode==MODE_A || partMode==MODE_B || partMode==MODE_CH10)){
        enterBrowser();
      } else {
        showToast("BROWSER A/B/DRUM","ONLY",900);
      }
    }
    return; // suppress short-press actions while held
  }

  if (pressed){
    pressed=false;
    if (!longFired){
      // SHORT PRESS
      if (splitOn){
        if (editMode==EDIT_NONE) editMode=EDIT_SPLIT;
        else if (editMode==EDIT_SPLIT) editMode=EDIT_LOCT;
        else if (editMode==EDIT_LOCT) editMode=EDIT_UOCT;
        else editMode=EDIT_SPLIT;
        dispDirty=true;
      } else if (uiMode==UI_BROWSER){
        browser.cursor = (browser.cursor+1)% (partMode==MODE_CH10 ? 1 : 3);
        dispDirty=true;
      } else {
        if (uiMode==UI_VOL) uiMode=UI_PC;
        else if (uiMode==UI_PC) uiMode=UI_RVB;
        else if (uiMode==UI_RVB) uiMode=UI_CHO;
        else if (uiMode==UI_CHO) uiMode=UI_CUT;
        else if (uiMode==UI_CUT) uiMode=UI_RES;
        else if (uiMode==UI_RES) uiMode=UI_MOD;
        else if (uiMode==UI_MOD) uiMode=UI_ATK;
        else if (uiMode==UI_ATK) uiMode=UI_REL;
        else uiMode=UI_PC;
        const char* t =
          (uiMode==UI_PC) ? "PC" :
          (uiMode==UI_RVB) ? "REVERB" :
          (uiMode==UI_CHO) ? "CHORUS" :
          (uiMode==UI_CUT) ? "CUTOFF" :
          (uiMode==UI_RES) ? "RESON" :
          (uiMode==UI_MOD) ? "MOD" :
          (uiMode==UI_ATK) ? "ATTACK" :
          (uiMode==UI_REL) ? "RELEASE" : "VOLUME";
        showToast("MODE", t, 500);
        dispDirty=true;
      }

  }
}


}

void handleEncoder(){
  int8_t d; noInterrupts(); d=enc_delta; enc_delta=0; interrupts(); if(!d) return;

  // Normalize encoder step to 1 per detent in SPLIT EDIT (avoid +2)
  if (splitOn && editMode!=EDIT_NONE){
    if (d>0) d=1; else if (d<0) d=-1;
    static unsigned long seLastStepAt=0; static int8_t seLastDir=0;
    unsigned long now=millis(); int8_t dir = (d>0)?1:-1;
    if ((now - seLastStepAt) < 110 && dir == seLastDir) return; // guard double-step
    seLastStepAt = now; seLastDir = dir; d = dir;
  }
// Clamp encoder delta to 1 step only in PROGRAM CHANGE mode
  if (uiMode==UI_PC){ if (d>0) d=1; else if (d<0) d=-1; }
  // For non-PC parameter UIs (VOL/RVB/CHO/CUT/RES/MOD/ATK/REL), enforce 4-per-detent behavior:
  if (uiMode==UI_VOL || uiMode==UI_RVB || uiMode==UI_CHO || uiMode==UI_CUT || uiMode==UI_RES || uiMode==UI_MOD || uiMode==UI_ATK || uiMode==UI_REL){
    if (d>0) d=+4; else if (d<0) d=-4; else return;
  }

  // Guard to avoid double-step per detent in PC mode (direction-aware)
  if (uiMode==UI_PC){
    static unsigned long pcLastStepAt=0;
    static int8_t pcLastDir=0;
    unsigned long now=millis();
    int8_t dir = (d>0) ? 1 : -1;
    // If a same-direction step arrives within the guard window, ignore it
    if ((now - pcLastStepAt) < 110 && dir == pcLastDir) return;
    pcLastStepAt = now;
    pcLastDir = dir;
    d = dir; // ensure magnitude of 1
  }

// --- Normalize Browser mode to 1 step per detent ---
  if (uiMode==UI_BROWSER){
    // Compress quadrature to 1 step per detent: accumulate edges until ±2
    static int8_t brAccum = 0;
    if (d>0) brAccum += 1;
    else if (d<0) brAccum -= 1;
    else return;
    if (brAccum >= 2){ d = 1; brAccum -= 2; }
    else if (brAccum <= -2){ d = -1; brAccum += 2; }
    else { return; } // wait until we have a full detent
  }

if (uiMode==UI_BROWSER){
    if (partMode==MODE_CH10){
      int k=(int)browser.kitIndex + d; if (k<0) k=0; if (k>=DKITS_COUNT) k=DKITS_COUNT-1;
      if (k != browser.kitIndex){
        browser.kitIndex=(uint8_t)k;
        DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
        sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
      }
      dispDirty=true; return;
    }
    if (browser.cursor==0){
      int fi=(int)browser.famIndex + d; if (fi<0) fi=0; if (fi>=FAMS_COUNT) fi=FAMS_COUNT-1;
      browser.famIndex=(uint8_t)fi;
      browser.program=famClampProg(browser.famIndex, browser.program); previewBrowserTone();
    } else if (browser.cursor==1){
      int p=(int)browser.program + d; if (p<0) p=0; if (p>127) p=127;
      p = famClampProg(browser.famIndex, p);
      browser.program=(uint8_t)p; previewBrowserTone(); if (partMode==MODE_A){ sendRawCC(CH_A,0,0); sendPC(CH_A,browser.program);} else if (partMode==MODE_B){ sendRawCC(CH_B,0,0); sendPC(CH_B,browser.program);} 
    } else {
      int v = (int)browser.lsb + d;
  v = (v % 128 + 128) % 128;
  browser.lsb = (uint8_t)v; previewBrowserTone();
    }
    dispDirty=true; return;
  }

  // Split edit
  if (splitOn && editMode!=EDIT_NONE){
    // Normalize to 1 per detent specifically for split edit
    if (d>0) d=+1; else if (d<0) d=-1; else d=0;
    if (editMode==EDIT_SPLIT){ int sp=(int)splitPoint+d; if(sp<0)sp=0; if(sp>127)sp=127; splitPoint=(uint8_t)sp; }
    else if (editMode==EDIT_LOCT){ lowerOct+=d*12; if(lowerOct<OCT_SHIFT_MIN)lowerOct=OCT_SHIFT_MIN; if(lowerOct>OCT_SHIFT_MAX)lowerOct=OCT_SHIFT_MAX; }
    else if (editMode==EDIT_UOCT){ upperOct+=d*12; if(upperOct<OCT_SHIFT_MIN)upperOct=OCT_SHIFT_MIN; if(upperOct>OCT_SHIFT_MAX)upperOct=OCT_SHIFT_MAX; }
    dispDirty=true; return;
  }

  if (uiMode==UI_VOL){
    int step = 3;
    if (partMode==MODE_AB){
      int a=(int)volA+d; if(a<0)a=0; if(a>127)a=127; if(a!=volA){volA=a; sendRawCC(CH_A,7,volA);}
      int b=(int)volB+d; if(b<0)b=0; if(b>127)b=127; if(b!=volB){volB=b; sendRawCC(CH_B,7,volB);}
    } else if (partMode==MODE_A){
      int v=(int)volA+d; if(v<0)v=0; if(v>127)v=127; if(v!=volA){volA=v; sendRawCC(CH_A,7,volA);}
    } else if (partMode==MODE_B){
      int v=(int)volB+d; if(v<0)v=0; if(v>127)v=127; if(v!=volB){volB=v; sendRawCC(CH_B,7,volB);}
    } else {
      int v=(int)volD+d; if(v<0)v=0; if(v>127)v=127; if(v!=volD){volD=v; sendRawCC(CH_DRUM,7,volD);}
    }
  } else if (uiMode==UI_PC){
    if (partMode==MODE_A){ int v=(int)progA+d; if(v<0)v=0; if(v>127)v=127; progA=(uint8_t)v; pcPendingA=true; pcDueA=millis()+PC_IDLE_MS; }
    else if (partMode==MODE_B){ int v=(int)progB+d; if(v<0)v=0; if(v>127)v=127; progB=(uint8_t)v; pcPendingB=true; pcDueB=millis()+PC_IDLE_MS; }
  
    else if (partMode==MODE_CH10 && !splitOn){
      int k=(int)browser.kitIndex + d; if (k<0) k=0; if (k>=DKITS_COUNT) k=DKITS_COUNT-1;
      if (k != browser.kitIndex){
        browser.kitIndex=(uint8_t)k;
        DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
        sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
      }
      dispDirty=true;
      return;
    }
}
  else if (uiMode==UI_RVB){
    if (partMode==MODE_AB){
      int a=(int)rvbA+d; if(a<0)a=0; if(a>127)a=127; if(a!=rvbA){rvbA=a; sendRawCC(CH_A,91,rvbA);}
      int b=(int)rvbB+d; if(b<0)b=0; if(b>127)b=127; if(b!=rvbB){rvbB=b; sendRawCC(CH_B,91,rvbB);}
    } else if (partMode==MODE_A){
      int v=(int)rvbA+d; if(v<0)v=0; if(v>127)v=127; if(v!=rvbA){rvbA=v; sendRawCC(CH_A,91,rvbA);}
    } else if (partMode==MODE_B){
      int v=(int)rvbB+d; if(v<0)v=0; if(v>127)v=127; if(v!=rvbB){rvbB=v; sendRawCC(CH_B,91,rvbB);}
    } else {
      int v=(int)rvbD+d; if(v<0)v=0; if(v>127)v=127; if(v!=rvbD){rvbD=v; sendRawCC(CH_DRUM,91,rvbD);}
    }
  } else if (uiMode==UI_CHO){
    if (partMode==MODE_AB){
      int a=(int)choA+d; if(a<0)a=0; if(a>127)a=127; if(a!=choA){choA=a; sendRawCC(CH_A,93,choA);}
      int b=(int)choB+d; if(b<0)b=0; if(b>127)b=127; if(b!=choB){choB=b; sendRawCC(CH_B,93,choB);}
    } else if (partMode==MODE_A){
      int v=(int)choA+d; if(v<0)v=0; if(v>127)v=127; if(v!=choA){choA=v; sendRawCC(CH_A,93,choA);}
    } else if (partMode==MODE_B){
      int v=(int)choB+d; if(v<0)v=0; if(v>127)v=127; if(v!=choB){choB=v; sendRawCC(CH_B,93,choB);}
    } else {
      int v=(int)choD+d; if(v<0)v=0; if(v>127)v=127; if(v!=choD){choD=v; sendRawCC(CH_DRUM,93,choD);}
    }
  } else if (uiMode==UI_CUT){
    if (partMode==MODE_AB){
      int a=(int)cutA+d; if(a<0)a=0; if(a>127)a=127; if(a!=cutA){cutA=a; sendRawCC(CH_A,74,cutA);}
      int b=(int)cutB+d; if(b<0)b=0; if(b>127)b=127; if(b!=cutB){cutB=b; sendRawCC(CH_B,74,cutB);}
    } else if (partMode==MODE_A){
      int v=(int)cutA+d; if(v<0)v=0; if(v>127)v=127; if(v!=cutA){cutA=v; sendRawCC(CH_A,74,cutA);}
    } else if (partMode==MODE_B){
      int v=(int)cutB+d; if(v<0)v=0; if(v>127)v=127; if(v!=cutB){cutB=v; sendRawCC(CH_B,74,cutB);}
    } else {
      int v=(int)cutD+d; if(v<0)v=0; if(v>127)v=127; if(v!=cutD){cutD=v; sendRawCC(CH_DRUM,74,cutD);}
    }
  } else if (uiMode==UI_RES){
    if (partMode==MODE_AB){
      int a=(int)resA+d; if(a<0)a=0; if(a>127)a=127; if(a!=resA){resA=a; sendRawCC(CH_A,71,resA);}
      int b=(int)resB+d; if(b<0)b=0; if(b>127)b=127; if(b!=resB){resB=b; sendRawCC(CH_B,71,resB);}
    } else if (partMode==MODE_A){
      int v=(int)resA+d; if(v<0)v=0; if(v>127)v=127; if(v!=resA){resA=v; sendRawCC(CH_A,71,resA);}
    } else if (partMode==MODE_B){
      int v=(int)resB+d; if(v<0)v=0; if(v>127)v=127; if(v!=resB){resB=v; sendRawCC(CH_B,71,resB);}
    } else {
      int v=(int)resD+d; if(v<0)v=0; if(v>127)v=127; if(v!=resD){resD=v; sendRawCC(CH_DRUM,71,resD);}
    }
  } else if (uiMode==UI_MOD){
    if (partMode==MODE_AB){
      int a=(int)modA+d; if(a<0)a=0; if(a>127)a=127; if(a!=modA){modA=a; sendRawCC(CH_A,1,modA);}
      int b=(int)modB+d; if(b<0)b=0; if(b>127)b=127; if(b!=modB){modB=b; sendRawCC(CH_B,1,modB);}
    } else if (partMode==MODE_A){
      int v=(int)modA+d; if(v<0)v=0; if(v>127)v=127; if(v!=modA){modA=v; sendRawCC(CH_A,1,modA);}
    } else if (partMode==MODE_B){
      int v=(int)modB+d; if(v<0)v=0; if(v>127)v=127; if(v!=modB){modB=v; sendRawCC(CH_B,1,modB);}
    } else {
      int v=(int)modD+d; if(v<0)v=0; if(v>127)v=127; if(v!=modD){modD=v; sendRawCC(CH_DRUM,1,modD);}
    }
  } else if (uiMode==UI_ATK){
    if (partMode==MODE_AB){
      int a=(int)atkA+d; if(a<0)a=0; if(a>127)a=127; if(a!=atkA){atkA=a; sendRawCC(CH_A,73,atkA);}
      int b=(int)atkB+d; if(b<0)b=0; if(b>127)b=127; if(b!=atkB){atkB=b; sendRawCC(CH_B,73,atkB);}
    } else if (partMode==MODE_A){
      int v=(int)atkA+d; if(v<0)v=0; if(v>127)v=127; if(v!=atkA){atkA=v; sendRawCC(CH_A,73,atkA);}
    } else if (partMode==MODE_B){
      int v=(int)atkB+d; if(v<0)v=0; if(v>127)v=127; if(v!=atkB){atkB=v; sendRawCC(CH_B,73,atkB);}
    } else {
      int v=(int)atkD+d; if(v<0)v=0; if(v>127)v=127; if(v!=atkD){atkD=v; sendRawCC(CH_DRUM,73,atkD);}
    }
  } else if (uiMode==UI_REL){
    if (partMode==MODE_AB){
      int a=(int)relA+d; if(a<0)a=0; if(a>127)a=127; if(a!=relA){relA=a; sendRawCC(CH_A,72,relA);}
      int b=(int)relB+d; if(b<0)b=0; if(b>127)b=127; if(b!=relB){relB=b; sendRawCC(CH_B,72,relB);}
    } else if (partMode==MODE_A){
      int v=(int)relA+d; if(v<0)v=0; if(v>127)v=127; if(v!=relA){relA=v; sendRawCC(CH_A,72,relA);}
    } else if (partMode==MODE_B){
      int v=(int)relB+d; if(v<0)v=0; if(v>127)v=127; if(v!=relB){relB=v; sendRawCC(CH_B,72,relB);}
    } else {
      int v=(int)relD+d; if(v<0)v=0; if(v>127)v=127; if(v!=relD){relD=v; sendRawCC(CH_DRUM,72,relD);}
    }
  }
    dispDirty=true;
}

void handleLoadSaveEdges(){
  // Browser: +/- buttons adjust MSB; hold to accelerate; wrap-around
  if (uiMode==UI_BROWSER){
    // one-shot clicks
    if (readBtn(dbLoad)){ // '-' click
      if (partMode==MODE_CH10){
        if (browser.kitIndex>0){
          browser.kitIndex--;
          DrumKit dk; memcpy_P(&dk,&DKITS[browser.kitIndex],sizeof(DrumKit));
          sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
        }
      } else {
        if (browser.cursor==0){ // Family -1
          if (browser.famIndex>0){
            browser.famIndex--;
            browser.program = famClampProg(browser.famIndex, browser.program);
          }
        } else if (browser.cursor==1){ // Program -1
          int p = (int)browser.program - 1;
          p = famClampProg(browser.famIndex, p);
          browser.program = (uint8_t)p;
        } else { // MSB -1 with wrap
          int v = (int)browser.lsb - 1;
          v = (v % 128 + 128) % 128;
          browser.lsb = (uint8_t)v;
        }
        previewBrowserTone();
      }
      dispDirty = true; return;
    }
    if (readBtn(dbSave)){ // '+' click
      if (partMode==MODE_CH10){
        if (browser.kitIndex+1<DKITS_COUNT){
          browser.kitIndex++;
          DrumKit dk; memcpy_P(&dk,&DKITS[browser.kitIndex],sizeof(DrumKit));
          sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
        }
      } else {
        if (browser.cursor==0){ // Family +1
          if (browser.famIndex+1<FAMS_COUNT){
            browser.famIndex++;
            browser.program = famClampProg(browser.famIndex, browser.program);
          }
        } else if (browser.cursor==1){ // Program +1
          int p = (int)browser.program + 1;
          p = famClampProg(browser.famIndex, p);
          browser.program = (uint8_t)p;
        } else { // MSB +1 with wrap
          int v = (int)browser.lsb + 1;
          v = (v % 128 + 128) % 128;
          browser.lsb = (uint8_t)v;
        }
        previewBrowserTone();
      }
      dispDirty = true; return;
    }

    // hold acceleration
    static unsigned long brRepPlusAt=0, brRepMinusAt=0;
    unsigned long now = millis();
    bool plusHeld  = (!dbSave.stable);
    bool minusHeld = (!dbLoad.stable);
    if (plusHeld  && brRepPlusAt==0)  brRepPlusAt  = now + 400;
    if (minusHeld && brRepMinusAt==0) brRepMinusAt = now + 400;

    if (plusHeld && brRepPlusAt && now >= brRepPlusAt){
      unsigned long held = now - dbSave.tchg;
      unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
      if (partMode==MODE_CH10){
        if (browser.kitIndex+1<DKITS_COUNT){
          browser.kitIndex++;
          DrumKit dk; memcpy_P(&dk,&DKITS[browser.kitIndex],sizeof(DrumKit));
          sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
        }
      } else {
        if (browser.cursor==0){ // Family +1
          if (browser.famIndex+1<FAMS_COUNT){
            browser.famIndex++;
            browser.program = famClampProg(browser.famIndex, browser.program);
          }
        } else if (browser.cursor==1){ // Program +1
          int p = (int)browser.program + 1;
          p = famClampProg(browser.famIndex, p);
          browser.program = (uint8_t)p;
        } else { // MSB +1 with wrap
          int v = (int)browser.lsb + 1;
          v = (v % 128 + 128) % 128;
          browser.lsb = (uint8_t)v;
        }
        previewBrowserTone();
      }
      dispDirty = true; brRepPlusAt = now + interval; return;
    } else if (!plusHeld){ brRepPlusAt = 0; }

    if (minusHeld && brRepMinusAt && now >= brRepMinusAt){
      unsigned long held = now - dbLoad.tchg;
      unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
      if (partMode==MODE_CH10){
        if (browser.kitIndex>0){
          browser.kitIndex--;
          DrumKit dk; memcpy_P(&dk,&DKITS[browser.kitIndex],sizeof(DrumKit));
          sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
        }
      } else {
        if (browser.cursor==0){ // Family -1
          if (browser.famIndex>0){
            browser.famIndex--;
            browser.program = famClampProg(browser.famIndex, browser.program);
          }
        } else if (browser.cursor==1){ // Program -1
          int p = (int)browser.program - 1;
          p = famClampProg(browser.famIndex, p);
          browser.program = (uint8_t)p;
        } else { // MSB -1 with wrap
          int v = (int)browser.lsb - 1;
          v = (v % 128 + 128) % 128;
          browser.lsb = (uint8_t)v;
        }
        previewBrowserTone();
      }
      dispDirty = true; brRepMinusAt = now + interval; return;
    } else if (!minusHeld){ brRepMinusAt = 0; }// other browser UI handled elsewhere
  }

  
  /*SPLIT_EDIT_BUTTONS*/
  if (splitOn && editMode!=EDIT_NONE){
    if (readBtn(dbSave)){
      if (editMode==EDIT_SPLIT){ if (splitPoint<127) splitPoint++; }
      else if (editMode==EDIT_LOCT){ lowerOct += 12; if (lowerOct>OCT_SHIFT_MAX) lowerOct=OCT_SHIFT_MAX; }
      else if (editMode==EDIT_UOCT){ upperOct += 12; if (upperOct>OCT_SHIFT_MAX) upperOct=OCT_SHIFT_MAX; }
      dispDirty=true; return;
    }
    if (readBtn(dbLoad)){
      if (editMode==EDIT_SPLIT){ if (splitPoint>0) splitPoint--; }
      else if (editMode==EDIT_LOCT){ lowerOct -= 12; if (lowerOct<OCT_SHIFT_MIN) lowerOct=OCT_SHIFT_MIN; }
      else if (editMode==EDIT_UOCT){ upperOct -= 12; if (upperOct<OCT_SHIFT_MIN) upperOct=OCT_SHIFT_MIN; }
      dispDirty=true; return;
    }
  
    // --- Auto-repeat for Edit (split/low oct/high oct) ---
    static unsigned long repSaveAt=0, repLoadAt=0;
    unsigned long now = millis();
    const bool saveDown = (!dbSave.stable);
    const bool loadDown = (!dbLoad.stable);
    // Seed timers on hold start
    if (saveDown && repSaveAt==0) repSaveAt = now + 400;
    if (loadDown && repLoadAt==0) repLoadAt = now + 400;
    // Held repeat handlers
    if (saveDown){
      if (repSaveAt && now >= repSaveAt){
        // do PLUS step
        if (editMode==EDIT_SPLIT){ if (splitPoint<127) splitPoint++; }
        else if (editMode==EDIT_LOCT){ lowerOct += 12; if (lowerOct>OCT_SHIFT_MAX) lowerOct=OCT_SHIFT_MAX; }
        else if (editMode==EDIT_UOCT){ upperOct += 12; if (upperOct>OCT_SHIFT_MAX) upperOct=OCT_SHIFT_MAX; }
        unsigned long held = now - dbSave.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        dispDirty=true; repSaveAt = now + interval; return;
      }
    } else {
      repSaveAt=0;
    }
    if (loadDown){
      if (repLoadAt && now >= repLoadAt){
        // do MINUS step
        if (editMode==EDIT_SPLIT){ if (splitPoint>0) splitPoint--; }
        else if (editMode==EDIT_LOCT){ lowerOct -= 12; if (lowerOct<OCT_SHIFT_MIN) lowerOct=OCT_SHIFT_MIN; }
        else if (editMode==EDIT_UOCT){ upperOct -= 12; if (upperOct<OCT_SHIFT_MIN) upperOct=OCT_SHIFT_MIN; }
        unsigned long held = now - dbLoad.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        dispDirty=true; repLoadAt = now + interval; return;
      }
    } else {
      repLoadAt=0;
    }
    
  }
if (restorePrompt){
    if (readBtn(dbLoad)) { restoreYes=true;  dispDirty=true; }
    if (readBtn(dbSave)) { restoreYes=false; dispDirty=true; }
    return;
}

  // Program Change +/- for A/B (not AB, not Drum)
  if (uiMode==UI_PC && !splitOn && partMode!=MODE_AB && partMode!=MODE_CH10){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_A){ if (progA<127) progA++; pcPendingA=true; pcDueA=millis()+PC_IDLE_MS; }
      else if (partMode==MODE_B){ if (progB<127) progB++; pcPendingB=true; pcDueB=millis()+PC_IDLE_MS; }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_A){ if (progA>0) progA--; pcPendingA=true; pcDueA=millis()+PC_IDLE_MS; }
      else if (partMode==MODE_B){ if (progB>0) progB--; pcPendingB=true; pcDueB=millis()+PC_IDLE_MS; }
      dispDirty=true;
    }
  }

  // Drum kits +/- when PC on Drum mode
  if (uiMode==UI_PC && partMode==MODE_CH10 && !splitOn){
    if (readBtn(dbSave)) { // +
      int k=(int)browser.kitIndex + 1; if (k>=DKITS_COUNT) k=DKITS_COUNT-1; browser.kitIndex=(uint8_t)k;
      DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
      sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      int k=(int)browser.kitIndex - 1; if (k<0) k=0; browser.kitIndex=(uint8_t)k;
      DrumKit dk; memcpy_P(&dk, &DKITS[browser.kitIndex], sizeof(DrumKit));
      sendRawCC(CH_DRUM,0,121); sendPC(CH_DRUM, dk.pc);
      dispDirty=true;
    }
  }

  // Volume +/- (buttons) in VOL mode
  if (uiMode==UI_VOL){
    static unsigned long repSaveAt=0, repLoadAt=0;
    unsigned long now = millis();

    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){
        if (volA<127){ volA++; sendRawCC(CH_A,7,volA); }
        if (volB<127){ volB++; sendRawCC(CH_B,7,volB); }
      } else if (partMode==MODE_A){
        if (volA<127){ volA++; sendRawCC(CH_A,7,volA); }
      } else if (partMode==MODE_B){
        if (volB<127){ volB++; sendRawCC(CH_B,7,volB); }
      } else { // MODE_CH10 (DRUM)
        if (volD<127){ volD++; sendRawCC(CH_DRUM,7,volD); }
      }
      dispDirty=true; repSaveAt = now + 400; return;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){
        if (volA>0){ volA--; sendRawCC(CH_A,7,volA); }
        if (volB>0){ volB--; sendRawCC(CH_B,7,volB); }
      } else if (partMode==MODE_A){
        if (volA>0){ volA--; sendRawCC(CH_A,7,volA); }
      } else if (partMode==MODE_B){
        if (volB>0){ volB--; sendRawCC(CH_B,7,volB); }
      } else { // MODE_CH10 (DRUM)
        if (volD>0){ volD--; sendRawCC(CH_DRUM,7,volD); }
      }
      dispDirty=true; repLoadAt = now + 400; return;
    }
  
    // Held-repeat in VOL mode
    if (!dbSave.stable){
      if (repSaveAt && now >= repSaveAt){
        unsigned long held = now - dbSave.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        // perform +
        if (partMode==MODE_AB){
          if (volA<127){ volA++; sendRawCC(CH_A,7,volA); }
          if (volB<127){ volB++; sendRawCC(CH_B,7,volB); }
        } else if (partMode==MODE_A){
          if (volA<127){ volA++; sendRawCC(CH_A,7,volA); }
        } else if (partMode==MODE_B){
          if (volB<127){ volB++; sendRawCC(CH_B,7,volB); }
        } else { // MODE_CH10
          if (volD<127){ volD++; sendRawCC(CH_DRUM,7,volD); }
        }
        dispDirty=true; repSaveAt = now + interval; return;
      }
    } else {
      repSaveAt=0;
    }
    if (!dbLoad.stable){
      if (repLoadAt && now >= repLoadAt){
        unsigned long held = now - dbLoad.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        // perform -
        if (partMode==MODE_AB){
          if (volA>0){ volA--; sendRawCC(CH_A,7,volA); }
          if (volB>0){ volB--; sendRawCC(CH_B,7,volB); }
        } else if (partMode==MODE_A){
          if (volA>0){ volA--; sendRawCC(CH_A,7,volA); }
        } else if (partMode==MODE_B){
          if (volB>0){ volB--; sendRawCC(CH_B,7,volB); }
        } else { // MODE_CH10
          if (volD>0){ volD--; sendRawCC(CH_DRUM,7,volD); }
        }
        dispDirty=true; repLoadAt = now + interval; return;
      }
    } else {
      repLoadAt=0;
    }

  }
// Reverb send +/-
  if (uiMode==UI_RVB && !splitOn){
    // Edge-triggered single steps
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (rvbA<127) rvbA++; if (rvbB<127) rvbB++; sendRawCC(CH_A,91,rvbA); sendRawCC(CH_B,91,rvbB); }
      else if (partMode==MODE_A){ if (rvbA<127) rvbA++; sendRawCC(CH_A,91,rvbA); }
      else if (partMode==MODE_B){ if (rvbB<127) rvbB++; sendRawCC(CH_B,91,rvbB); }
      else { if (rvbD<127) rvbD++; sendRawCC(CH_DRUM,91,rvbD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (rvbA>0) rvbA--; if (rvbB>0) rvbB--; sendRawCC(CH_A,91,rvbA); sendRawCC(CH_B,91,rvbB); }
      else if (partMode==MODE_A){ if (rvbA>0) rvbA--; sendRawCC(CH_A,91,rvbA); }
      else if (partMode==MODE_B){ if (rvbB>0) rvbB--; sendRawCC(CH_B,91,rvbB); }
      else { if (rvbD>0) rvbD--; sendRawCC(CH_DRUM,91,rvbD); }
      dispDirty=true;
    }

    // Hold-to-accelerate auto-repeat
    static unsigned long repSaveAt_91=0, repLoadAt_91=0;
    unsigned long now_91 = millis();

    // Seed timers on hold start
    if (!dbSave.stable && repSaveAt_91==0) repSaveAt_91 = now_91 + 400;
    if (!dbLoad.stable && repLoadAt_91==0) repLoadAt_91 = now_91 + 400;

    // '+' held
    if (!dbSave.stable) {
      if (repSaveAt_91 && now_91 >= repSaveAt_91) {
        unsigned long held = now_91 - dbSave.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        if (partMode==MODE_AB){ if (rvbA<127) rvbA++; if (rvbB<127) rvbB++; sendRawCC(CH_A,91,rvbA); sendRawCC(CH_B,91,rvbB); }
        else if (partMode==MODE_A){ if (rvbA<127) rvbA++; sendRawCC(CH_A,91,rvbA); }
        else if (partMode==MODE_B){ if (rvbB<127) rvbB++; sendRawCC(CH_B,91,rvbB); }
        else { if (rvbD<127) rvbD++; sendRawCC(CH_DRUM,91,rvbD); }
        dispDirty=true; repSaveAt_91 = now_91 + interval; 
      }
    } else {
      repSaveAt_91 = 0;
    }

    // '-' held
    if (!dbLoad.stable) {
      if (repLoadAt_91 && now_91 >= repLoadAt_91) {
        unsigned long held = now_91 - dbLoad.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        if (partMode==MODE_AB){ if (rvbA>0) rvbA--; if (rvbB>0) rvbB--; sendRawCC(CH_A,91,rvbA); sendRawCC(CH_B,91,rvbB); }
        else if (partMode==MODE_A){ if (rvbA>0) rvbA--; sendRawCC(CH_A,91,rvbA); }
        else if (partMode==MODE_B){ if (rvbB>0) rvbB--; sendRawCC(CH_B,91,rvbB); }
        else { if (rvbD>0) rvbD--; sendRawCC(CH_DRUM,91,rvbD); }
        dispDirty=true; repLoadAt_91 = now_91 + interval; 
      }
    } else {
      repLoadAt_91 = 0;
    }
  }

  // Chorus send +/-
  if (uiMode==UI_CHO && !splitOn){
    // Edge-triggered single steps
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (choA<127) choA++; if (choB<127) choB++; sendRawCC(CH_A,93,choA); sendRawCC(CH_B,93,choB); }

  // Cutoff +/- (UI_CUT)
  if (uiMode==UI_CUT && !splitOn){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (cutA<127) cutA++; if (cutB<127) cutB++; sendRawCC(CH_A,74,cutA); sendRawCC(CH_B,74,cutB); }
      else if (partMode==MODE_A){ if (cutA<127) cutA++; sendRawCC(CH_A,74,cutA); }
      else if (partMode==MODE_B){ if (cutB<127) cutB++; sendRawCC(CH_B,74,cutB); }
      else { if (cutD<127) cutD++; sendRawCC(CH_DRUM,74,cutD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (cutA>0) cutA--; if (cutB>0) cutB--; sendRawCC(CH_A,74,cutA); sendRawCC(CH_B,74,cutB); }
      else if (partMode==MODE_A){ if (cutA>0) cutA--; sendRawCC(CH_A,74,cutA); }
      else if (partMode==MODE_B){ if (cutB>0) cutB--; sendRawCC(CH_B,74,cutB); }
      else { if (cutD>0) cutD--; sendRawCC(CH_DRUM,74,cutD); }
      dispDirty=true;
    }
  }

  // Resonance +/- (UI_RES)
  if (uiMode==UI_RES && !splitOn){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (resA<127) resA++; if (resB<127) resB++; sendRawCC(CH_A,71,resA); sendRawCC(CH_B,71,resB); }
      else if (partMode==MODE_A){ if (resA<127) resA++; sendRawCC(CH_A,71,resA); }
      else if (partMode==MODE_B){ if (resB<127) resB++; sendRawCC(CH_B,71,resB); }
      else { if (resD<127) resD++; sendRawCC(CH_DRUM,71,resD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (resA>0) resA--; if (resB>0) resB--; sendRawCC(CH_A,71,resA); sendRawCC(CH_B,71,resB); }
      else if (partMode==MODE_A){ if (resA>0) resA--; sendRawCC(CH_A,71,resA); }
      else if (partMode==MODE_B){ if (resB>0) resB--; sendRawCC(CH_B,71,resB); }
      else { if (resD>0) resD--; sendRawCC(CH_DRUM,71,resD); }
      dispDirty=true;
    }
  }

  // ModWheel +/- (UI_MOD)
  if (uiMode==UI_MOD && !splitOn){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (modA<127) modA++; if (modB<127) modB++; sendRawCC(CH_A,1,modA); sendRawCC(CH_B,1,modB); }
      else if (partMode==MODE_A){ if (modA<127) modA++; sendRawCC(CH_A,1,modA); }
      else if (partMode==MODE_B){ if (modB<127) modB++; sendRawCC(CH_B,1,modB); }
      else { if (modD<127) modD++; sendRawCC(CH_DRUM,1,modD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (modA>0) modA--; if (modB>0) modB--; sendRawCC(CH_A,1,modA); sendRawCC(CH_B,1,modB); }
      else if (partMode==MODE_A){ if (modA>0) modA--; sendRawCC(CH_A,1,modA); }
      else if (partMode==MODE_B){ if (modB>0) modB--; sendRawCC(CH_B,1,modB); }
      else { if (modD>0) modD--; sendRawCC(CH_DRUM,1,modD); }
      dispDirty=true;
    }
  }

  // Attack +/- (UI_ATK)
  if (uiMode==UI_ATK && !splitOn){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (atkA<127) atkA++; if (atkB<127) atkB++; sendRawCC(CH_A,73,atkA); sendRawCC(CH_B,73,atkB); }
      else if (partMode==MODE_A){ if (atkA<127) atkA++; sendRawCC(CH_A,73,atkA); }
      else if (partMode==MODE_B){ if (atkB<127) atkB++; sendRawCC(CH_B,73,atkB); }
      else { if (atkD<127) atkD++; sendRawCC(CH_DRUM,73,atkD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (atkA>0) atkA--; if (atkB>0) atkB--; sendRawCC(CH_A,73,atkA); sendRawCC(CH_B,73,atkB); }
      else if (partMode==MODE_A){ if (atkA>0) atkA--; sendRawCC(CH_A,73,atkA); }
      else if (partMode==MODE_B){ if (atkB>0) atkB--; sendRawCC(CH_B,73,atkB); }
      else { if (atkD>0) atkD--; sendRawCC(CH_DRUM,73,atkD); }
      dispDirty=true;
    }
  }

  // Release +/- (UI_REL)
  if (uiMode==UI_REL && !splitOn){
    if (readBtn(dbSave)) { // +
      if (partMode==MODE_AB){ if (relA<127) relA++; if (relB<127) relB++; sendRawCC(CH_A,72,relA); sendRawCC(CH_B,72,relB); }
      else if (partMode==MODE_A){ if (relA<127) relA++; sendRawCC(CH_A,72,relA); }
      else if (partMode==MODE_B){ if (relB<127) relB++; sendRawCC(CH_B,72,relB); }
      else { if (relD<127) relD++; sendRawCC(CH_DRUM,72,relD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (relA>0) relA--; if (relB>0) relB--; sendRawCC(CH_A,72,relA); sendRawCC(CH_B,72,relB); }
      else if (partMode==MODE_A){ if (relA>0) relA--; sendRawCC(CH_A,72,relA); }
      else if (partMode==MODE_B){ if (relB>0) relB--; sendRawCC(CH_B,72,relB); }
      else { if (relD>0) relD--; sendRawCC(CH_DRUM,72,relD); }
      dispDirty=true;
    }
  }

      else if (partMode==MODE_A){ if (choA<127) choA++; sendRawCC(CH_A,93,choA); }
      else if (partMode==MODE_B){ if (choB<127) choB++; sendRawCC(CH_B,93,choB); }
      else { if (choD<127) choD++; sendRawCC(CH_DRUM,93,choD); }
      dispDirty=true;
    }
    if (readBtn(dbLoad)) { // -
      if (partMode==MODE_AB){ if (choA>0) choA--; if (choB>0) choB--; sendRawCC(CH_A,93,choA); sendRawCC(CH_B,93,choB); }
      else if (partMode==MODE_A){ if (choA>0) choA--; sendRawCC(CH_A,93,choA); }
      else if (partMode==MODE_B){ if (choB>0) choB--; sendRawCC(CH_B,93,choB); }
      else { if (choD>0) choD--; sendRawCC(CH_DRUM,93,choD); }
      dispDirty=true;
    }

    // Hold-to-accelerate auto-repeat
    static unsigned long repSaveAt_93=0, repLoadAt_93=0;
    unsigned long now_93 = millis();

    // Seed timers on hold start
    if (!dbSave.stable && repSaveAt_93==0) repSaveAt_93 = now_93 + 400;
    if (!dbLoad.stable && repLoadAt_93==0) repLoadAt_93 = now_93 + 400;

    // '+' held
    if (!dbSave.stable) {
      if (repSaveAt_93 && now_93 >= repSaveAt_93) {
        unsigned long held = now_93 - dbSave.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        if (partMode==MODE_AB){ if (choA<127) choA++; if (choB<127) choB++; sendRawCC(CH_A,93,choA); sendRawCC(CH_B,93,choB); }
        else if (partMode==MODE_A){ if (choA<127) choA++; sendRawCC(CH_A,93,choA); }
        else if (partMode==MODE_B){ if (choB<127) choB++; sendRawCC(CH_B,93,choB); }
        else { if (choD<127) choD++; sendRawCC(CH_DRUM,93,choD); }
        dispDirty=true; repSaveAt_93 = now_93 + interval; 
      }
    } else {
      repSaveAt_93 = 0;
    }

    // '-' held
    if (!dbLoad.stable) {
      if (repLoadAt_93 && now_93 >= repLoadAt_93) {
        unsigned long held = now_93 - dbLoad.tchg;
        unsigned long interval = (held>3500 ? 30 : (held>1800 ? 60 : 120));
        if (partMode==MODE_AB){ if (choA>0) choA--; if (choB>0) choB--; sendRawCC(CH_A,93,choA); sendRawCC(CH_B,93,choB); }
        else if (partMode==MODE_A){ if (choA>0) choA--; sendRawCC(CH_A,93,choA); }
        else if (partMode==MODE_B){ if (choB>0) choB--; sendRawCC(CH_B,93,choB); }
        else { if (choD>0) choD--; sendRawCC(CH_DRUM,93,choD); }
        dispDirty=true; repLoadAt_93 = now_93 + interval; 
      }
    } else {
      repLoadAt_93 = 0;
    }
  }

}

void handlePartBtnAnalog(){
  if (!readPartAnalogPressed(dbPart)) return;
  allNotesOffAllCh(); // silence once on confirmed PART press edge
  if (restorePrompt) return;

  // Enter/Stay in SINGLE-CHANNEL mode and cycle: A -> B -> Drum -> A
  splitOn = false;           // ensure single mode
  editMode = EDIT_NONE;
  if (partMode==MODE_A) partMode=MODE_B;
  else if (partMode==MODE_B) partMode=MODE_CH10;
  else /* MODE_CH10 or others */ partMode=MODE_A;

  lastSinglePart = partMode; // remember last single-channel state
  if (uiMode==UI_BROWSER) uiMode=UI_VOL; // exit browser on part change
  // refresh LEDs and LCD
  ledState(); dispDirty=true;
}

void handleSplitBtn(){
  if (!readBtn(dbSplit)) return;
  if (splitOn){
    // Split -> A+B layer
    splitOn = false;
    partMode = MODE_AB;
    editMode = EDIT_NONE;
  } else {
    if (partMode == MODE_AB){
      // A+B -> Split
      splitOn = true;
      editMode = EDIT_NONE;
      splitBlinkOn = true;
      splitBlinkNext = millis() + SPLIT_BLINK_MS;
    } else {
      // Single -> A+B layer
      splitOn = false;
      partMode = MODE_AB;
      editMode = EDIT_NONE;
    }
  }
  ledState(); dispDirty=true;
}
void handleStopBtn(){
  if (!readBtn(dbStop)) return;
  if (uiMode==UI_BROWSER){ exitBrowser(false); return; }
  if (splitOn && editMode!=EDIT_NONE){ editMode=EDIT_NONE; dispDirty=true; return; }
if (splitOn || partMode==MODE_AB){
    // In MULTI-CHANNEL mode, return to the last SINGLE-CHANNEL state
    splitOn = false;
    editMode = EDIT_NONE;
    lowerOct = 0; upperOct = 0; // keep previous behavior
    partMode = lastSinglePart;
    uiMode = UI_VOL;
  } else {
    // Already in SINGLE-CHANNEL mode: default to A (as before)
    partMode = MODE_A;
    uiMode = UI_VOL;
  }
  ledState(); dispDirty=true;
}

// ---------- Setup & main loop ----------
void setup(){
  char id[24]; strncpy_P(id, BUILD_ID, sizeof(id)-1); id[sizeof(id)-1]=0;
  lastSinglePart = MODE_A; splitBlinkOn=true; splitBlinkNext=millis()+SPLIT_BLINK_MS;
  pinMode(LED_A_PIN,OUTPUT); pinMode(LED_B_PIN,OUTPUT); pinMode(LED_DRUM_PIN,OUTPUT);
  pinMode(LED_ACTIVITY,OUTPUT); digitalWrite(LED_ACTIVITY,LOW);
  pinMode(ENC_A_PIN,INPUT_PULLUP); pinMode(ENC_B_PIN,INPUT_PULLUP); pinMode(ENC_SW_PIN,INPUT_PULLUP);
  pinMode(BTN_SPLIT_PIN,INPUT_PULLUP); pinMode(BTN_STOP_PIN,INPUT_PULLUP);
  pinMode(BTN_LOAD_PIN,INPUT_PULLUP); pinMode(BTN_SAVE_PIN,INPUT_PULLUP);
  analogReference(DEFAULT);
  enc_state=((uint8_t)digitalRead(ENC_A_PIN)<<1)|(uint8_t)digitalRead(ENC_B_PIN);
  attachInterrupt(digitalPinToInterrupt(ENC_A_PIN),enc_isr,CHANGE);
  attachInterrupt(digitalPinToInterrupt(ENC_B_PIN),enc_isr,CHANGE);
  lcd.init(); lcd.backlight(); lcd.clear();
  lcd.setCursor(0,0); print16("Nano Ardule");
{
  char wbuf[17];
  const char* p = id;
  size_t L = strlen(id);
  if (L > 7) p = id + (L - 7);  // show last 7 chars if longer
  snprintf(wbuf, sizeof(wbuf), "Welcome! %-7.7s", p); // total 16 chars
  lcd.setCursor(0,1); print16(wbuf);
}
delay(1200);
  // (BUILD_ID merged into Welcome splash; separate screen removed)
  Serial.begin(MIDI_BAUD);
  // Initial setup
  sendPC(CH_A, progA); sendPC(CH_B, progB);
  sendRawCC(CH_A,7,volA); sendRawCC(CH_B,7,volB); sendRawCC(CH_DRUM,7,volD);
  sendRawCC(CH_A,91,rvbA); sendRawCC(CH_B,91,rvbB); sendRawCC(CH_DRUM,91,rvbD);
  sendRawCC(CH_A,93,choA); sendRawCC(CH_B,93,choB); sendRawCC(CH_DRUM,93,choD);
  ledState(); dispDirty=true;
}
void flushPendingPC(){
  unsigned long now=millis();
  if (pcPendingA && now>=pcDueA){ sendBankAndProgram(CH_A, bankMSB_A, bankLSB_A, bankMSB_A, 0, progA); pcPendingA=false; }
  if (pcPendingB && now>=pcDueB){ sendBankAndProgram(CH_B, bankMSB_B, bankLSB_B, bankMSB_B, 0, progB); pcPendingB=false; }
}
void loop(){
  while (Serial.available()>0){ uint8_t b=(uint8_t)Serial.read(); handleMidiByte(b); }
  handlePartBtnAnalog();
  handleSplitBtn();
  handleStopBtn();
  handleEncoderBtn();
  handleEncoder();
  handleLoadSaveEdges();
  flushPendingPC();
  renderLCD();
  // Auto-sync blink state based on uiMode
  {
    bool desired = ((uiMode!=UI_VOL) || (splitOn && editMode!=EDIT_NONE));
    if (partBlinkActive != desired){ partBlinkActive = desired; partBlinkOn=true; partBlinkNext=millis()+((uiMode==UI_BROWSER)?BROWSER_BLINK_MS:PART_LED_BLINK_MS); ledState(); }
  }
  // Toggle part LED blink if active
  if (partBlinkActive && millis()>=partBlinkNext){ partBlinkOn=!partBlinkOn; partBlinkNext+=((uiMode==UI_BROWSER)?BROWSER_BLINK_MS:PART_LED_BLINK_MS); ledState(); }
  if (ledOffAt && millis()>=ledOffAt){ digitalWrite(LED_ACTIVITY,LOW); ledOffAt=0; }
  // Toggle Split LED alternate blink
  if (splitOn && millis()>=splitBlinkNext){ 
    unsigned long __blinkInterval = (editMode!=EDIT_NONE) ? (SPLIT_BLINK_MS/2) : SPLIT_BLINK_MS;
    splitBlinkOn = !splitBlinkOn;
    splitBlinkNext += __blinkInterval;
    ledState();
  }
}