# ADT v2.2a Specification
**Ardule Drum Text Format**

> Version: v2.2a  
> Status: Stable / Public specification

---

## 1. Introduction

ADT (Ardule Drum Text) is a human-readable text format for representing
**two-bar drum patterns** on a fixed rhythmic grid.

This document defines the **authoritative specification** of ADT v2.2a.

---

## 2. Core Concepts

An ADT pattern represents:
- Exactly **2 bars**
- A **fixed grid** (straight or triplet)
- A set of **drum slots** (one instrument per row)
- **Relative velocity levels** per step

---

## 3. File Structure

An ADT file consists of:
1. Header (metadata)
2. Slot definitions
3. Pattern body

---

## 4. Header Section

Header lines start with `#`.

Common fields:
- `GRID`   : grid type
- `LENGTH` : total steps (always 2 bars)
- `TS`     : time signature (semantic hint)
- `BPM`    : tempo hint
- `KIT`    : drum kit hint

---

## 5. Grid and Length

| GRID | Meaning | LENGTH |
|------|--------|--------|
| 16   | Straight 16th grid | 32 |
| 8T   | 8th-note triplet grid | 24 |
| 16T  | 16th-note triplet grid | 48 |

---

## 6. Slot Definitions

```
SLOT <NAME> <MIDI_NOTE>
```

---

## 7. Velocity Representation

ADT defines **four velocity levels**, represented by symbols:

| Level | Meaning | Symbol |
|------:|--------|--------|
| 0 | Rest | `.` |
| 1 | Soft | `-` |
| 2 | Medium | `x` / `X` |
| 3 | Strong | `o` / `O` |

Canonical order (low → high):

```
.  -  x  o
```

Symbols are **case-insensitive**.

---

## 8. Recommended Velocity-to-MIDI Mapping

ADT encodes **relative** velocity only.  
Playback engines and converters SHOULD map symbols to MIDI velocity
using a consistent table.

### Recommended Default Mapping

| Symbol | Level | Suggested MIDI Velocity |
|--------|-------|--------------------------|
| `.` | 0 | — (no note) |
| `-` | 1 | 40–60 |
| `x` / `X` | 2 | 80–100 |
| `o` / `O` | 3 | 115–127 |

Notes:
- Exact values MAY be tuned per engine or kit
- The table defines **relative loudness**, not absolute dynamics
- Strong hits (`O`) SHOULD be clearly accented

---

## 9. Pattern Body Rules

- Each row contains exactly `LENGTH` symbols
- Whitespace is ignored
- One row represents a single logical slot
- In rotated represntation, a row instead corresponds to an instrument layout

---

## 10. Complete Example

```text
; ADT v2.2a
NAME=BLU_P001
TIME_SIG=4/4
GRID=8T
LENGTH=24
SLOTS=12
KIT=GM_STD
ORIENTATION=SLOT
SLOT0=KK@36,KICK
SLOT1=SN@38,SNARE
SLOT2=CH@42,HH_CL
SLOT3=OH@46,HH_OP
SLOT4=LT@45,TOM_L
SLOT5=MT@47,TOM_M
SLOT6=HT@50,TOM_H
SLOT7=RD@51,RIDE
SLOT8=CR@49,CRASH
SLOT9=RM@37,RIM
SLOT10=CL@39,CLAP
SLOT11=PH@44,HH_PED
x.x..xx.x.xxx.x..xx.x.xx
...x.....x.....x.....x..
xxxxxxxxxxxxxxxxxxxxxxxx
........................
........................
........................
........................
........................
........................
........................
........................
........................

```

---

## 11. Parsing and Playback

- ADT encodes structure, not performance
- Playback engines derive timing from GRID/LENGTH
- Velocity mapping follows Section 8

---

## 12. License

This specification is released under the same license as the Ardule project.
