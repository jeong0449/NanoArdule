# ADT v2.2a Specification
**Ardule Drum Text Format**

> Version: v2.2a
> Status: Stable / Public Specification
>
> **Revision (2026-07-31)**
>
> This document has been revised to accurately describe the current ADT v2.2a
> implementation used by the Ardule Drum Patternology ecosystem. No file format
> changes have been introduced. This revision updates terminology, metadata
> definitions, examples, and parsing rules while maintaining full backward
> compatibility with existing ADT v2.2a files.

---

# 1. Introduction

ADT (Ardule Drum Text) is a human-readable text format for representing drum
patterns. It is intended to be simple enough for manual editing while remaining
easy to parse by software.

An ADT file consists of metadata, slot definitions and a pattern body.

---

# 2. Core Concepts

An ADT pattern contains:

- Musical metadata
- A rhythmic grid
- Drum slot definitions
- Relative velocity symbols
- Pattern data

ADT represents musical structure rather than MIDI events.

---

# 3. File Structure

An ADT file is composed of:

1. Header (KEY=VALUE pairs)
2. Slot definitions
3. Pattern body

Comment lines begin with ';'.

---

# 4. Header

Header fields use:

KEY=VALUE

Common fields

| Field | Description |
|------|-------------|
| NAME | Pattern identifier |
| TIME_SIG | Time signature (4/4, 3/4, 6/8...) |
| GRID | Rhythmic grid |
| LENGTH | Total stored steps |
| SLOTS | Number of slot definitions |
| KIT | Drum kit identifier |
| ORIENTATION | STEP or SLOT |

---

# 5. GRID and LENGTH

GRID specifies the **smallest rhythmic note value used to construct one beat**.

It does **not** indicate the number of subdivisions per beat.

Typical values are:

| GRID | Meaning | Steps per Beat |
|------|---------|---------------:|
|16|Sixteenth-note grid|4|
|8T|Eighth-note triplet grid|3|
|16T|Sixteenth-note triplet grid|6|

LENGTH specifies the total number of stored pattern steps (one pattern = two bars).

Examples:

| TIME_SIG | GRID | LENGTH |
|----------|------|--------|
|4/4|16|32|
|3/4|16|24|
|4/4|8T|24|
|4/4|16T|48|

---

# 6. Slot Definitions

Each slot uses:

SLOTn=<SHORT>@<MIDI>,<LONG>

Example

SLOT0=KK@36,KICK
SLOT1=SN@38,SNARE

---

# 7. Velocity Symbols

| Symbol | Meaning |
|--------|---------|
| . | Rest |
| - | Soft |
| x/X | Medium |
| o/O | Strong |

Symbols are case-insensitive.

---

# 8. Pattern Body

Each row contains exactly LENGTH symbols.

Whitespace outside pattern symbols is ignored.

When ORIENTATION=STEP each row represents one time step.

When ORIENTATION=SLOT each row represents one instrument slot.

---

# 9. Example

```text
; ADT v2.2a
NAME=AFC_B015
TIME_SIG=4/4
GRID=16
LENGTH=32
SLOTS=12
KIT=GM_STD
ORIENTATION=STEP
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
.-..........
............
.-..........
```

---

# 10. Parsing

A parser shall:

- Read metadata.
- Read SLOT definitions.
- Verify row lengths equal LENGTH.
- Interpret GRID as rhythmic resolution.
- Interpret velocity symbols relatively.

Playback timing is derived from TIME_SIG, GRID and LENGTH.

---

# 11. Compatibility

This revision documents the existing ADT v2.2a implementation only.

No syntax has been added, removed or modified.

---

# 12. License

Released under the same license as the Ardule project.
