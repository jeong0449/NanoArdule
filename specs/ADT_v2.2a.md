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

- Each row has exactly `LENGTH` symbols
- Whitespace is ignored
- One row per slot

---

## 10. Complete Example

```text
# ADT v2.2a
# GRID=16 LENGTH=32 TS=4/4 BPM=120
# KIT=GM_STD

SLOT KICK   36
SLOT SNARE  38
SLOT HH_C   42

KICK  : o... .... o... .... o... .... o.-. ....
SNARE : .... o... .... o... .... o... .... o...
HH_C  : x.x. x.x. x.x. x.x. x.x. x.x. x.x. x.x.
```

---

## 11. Parsing and Playback

- ADT encodes structure, not performance
- Playback engines derive timing from GRID/LENGTH
- Velocity mapping follows Section 8

---

## 12. License

This specification is released under the same license as the Ardule project.
