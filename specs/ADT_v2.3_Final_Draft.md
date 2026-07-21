# ADT v2.3 Specification
**Ardule Drum Text Format**

| Item | Value |
|------|-------|
| First published | 2026-07-21 |
| Last updated | 2026-07-21 |
| Version | v2.3 Draft (Not Yet Implemented) |
| Status | Draft |

---

# 1. Introduction

ADT (Ardule Drum Text) is a human-readable drum pattern format used by APS
(Ardule Pattern Studio) and Fluid Ardule.

Version 2.3 is the first revision designed with the explicit goal of supporting
**arbitrary musical time signatures**, while preserving compatibility with the
existing ADT v2.2 family whenever practical.

This document is a **specification only**.

At the time this specification is published, APS and Fluid Ardule have **not**
implemented the generalized time-signature system described here. Existing
software may therefore support only traditional 4/4 patterns.

---

# 2. Design Philosophy

ADT is intended to describe **rhythmic events**, not conventional music
notation.

Accordingly,

- playback engines should depend only on rhythmic resolution and pattern length;
- musical notation should remain metadata useful for editing, validation and UI;
- the format should remain readable without specialized software.

---

# 3. Design Goals

1. Preserve backward compatibility.
2. Support arbitrary time signatures.
3. Keep parser changes minimal.
4. Keep playback implementation simple.
5. Maintain a plain-text format.

---

# 4. File Organization

Each ADT file consists of:

- Header section
- Drum rows

The overall organization remains compatible with ADT v2.2.

---

# 5. Header Fields

Recommended fields:

```
NAME
AUTHOR
VERSION
TIME_SIG
GRID
LENGTH
BPM
COMMENT
```

Applications may introduce additional fields.

---

# 6. TIME_SIG

Syntax

```
TIME_SIG=numerator/denominator
```

Examples

```
TIME_SIG=4/4
TIME_SIG=3/4
TIME_SIG=5/4
TIME_SIG=7/8
TIME_SIG=9/8
TIME_SIG=12/8
```

TIME_SIG represents the musical meter shown to the user.

Playback engines are not required to derive timing directly from TIME_SIG.

---

# 7. GRID

GRID defines rhythmic resolution.

| GRID | Steps per whole note |
|------|----------------------:|
|16|16|
|8T|12|
|16T|24|

Future revisions may introduce additional values.

---

# 8. LENGTH

Unlike ADT v2.2, LENGTH is no longer fixed by GRID alone.

LENGTH represents the actual number of playback steps contained in the pattern.

For the current ADT two-bar pattern:

```
LENGTH =
2 × numerator × steps_per_whole_note ÷ denominator
```

Examples

| Meter | GRID | LENGTH |
|------|------|-------:|
|4/4|16|32|
|3/4|16|24|
|5/4|16|40|
|7/8|16|28|
|9/8|16|36|
|12/8|16|48|

Implementations SHOULD verify that LENGTH is consistent with TIME_SIG and GRID.

---

# 9. Drum Rows

Every drum row SHALL contain exactly LENGTH symbols.

Example

```
KICK : X...X...X...X...
SNARE: ....X.......X...
HHAT : X.X.X.X.X.X.X.X.
```

---

# 10. Symbols

Minimum symbol set

| Symbol | Meaning |
|---------|---------|
|X|Note On|
|.|Rest|

Applications MAY define additional symbols.

---

# 11. Validation

A valid ADT file SHALL satisfy:

- valid TIME_SIG
- supported GRID
- valid LENGTH
- every drum row length equals LENGTH

---

# 12. Playback Semantics

Playback timing is determined by:

- GRID
- LENGTH

TIME_SIG is primarily intended for:

- editor display
- validation
- navigation
- future metronome/accent display

---

# 13. Backward Compatibility

Existing ADT v2.2 4/4 files remain valid.

No changes are required for:

```
TIME_SIG=4/4
GRID=16
LENGTH=32
```

Software may continue to support only 4/4 while remaining compliant with a
subset of this specification.

---

# 14. Examples

## 4/4

```
TIME_SIG=4/4
GRID=16
LENGTH=32
```

## 3/4

```
TIME_SIG=3/4
GRID=16
LENGTH=24
```

## 5/4

```
TIME_SIG=5/4
GRID=16
LENGTH=40
```

## 7/8

```
TIME_SIG=7/8
GRID=16
LENGTH=28
```

## 12/8

```
TIME_SIG=12/8
GRID=16
LENGTH=48
```

---

# 15. Implementation Strategy

The specification intentionally precedes implementation.

A recommended implementation order is:

1. 3/4
2. 5/4
3. Generalized LENGTH
4. Arbitrary N/4
5. Arbitrary N/8

---

# 16. Future Extensions

Possible future additions include:

- Accent grouping (2+2+3)
- Swing metadata
- Variable number of bars
- Additional GRID values
- Per-track options

These features are outside the scope of ADT v2.3.

---

# 17. Revision History

## v2.3 (Draft)

- Generalized TIME_SIG.
- Generalized LENGTH calculation.
- Preserved file structure.
- Preserved backward compatibility.
- Published before implementation.
