<!DOCTYPE markdown>

# ADT v2.2b Specification
### (Meter-Generalized Clarification Release)

**Status**: Clarification / Documentation Update  
**Compatibility**: Fully backward-compatible with v2.2a  
**Scope**: Semantic clarification for arbitrary time signatures

---

## 0. Overview

ADT (Ardule Drum Pattern Text) format represents drum patterns as a fixed-length
sequence of time-aligned steps.

ADT v2.2b does **not** introduce any structural changes to the file format.
Instead, it formally clarifies that ADT patterns are **not restricted to 4/4
time**, and that **arbitrary time signatures are valid and supported**.

The playback engine continues to rely solely on `LENGTH` and `GRID`.
`TIME_SIG` is elevated from a purely informational hint to a **formally defined
musical metadata field**, usable for validation and editor behavior.

---

## 1. Header Fields

### 1.1 TIME_SIG (or TS)

TIME_SIG defines the musical time signature of the pattern, expressed as:

```
beats_per_bar / note_value
```

Examples:
- `TIME_SIG=4/4`
- `TIME_SIG=3/4`
- `TIME_SIG=7/8`

TIME_SIG is primarily intended for:
- human readability
- editing and visualization
- musical interpretation

Playback engines may ignore TIME_SIG and operate solely on `LENGTH` and `GRID`.

When present, TIME_SIG **may be used together with GRID to derive or validate
the expected pattern length**.

---

### 1.2 GRID

GRID defines the temporal resolution of the pattern relative to a quarter note.

Common values include:

| GRID | Meaning |
|-----:|---------|
| 16   | 16th notes (straight) |
| 8T   | 8th-note triplets |
| 16T  | 16th-note triplets |

GRID determines the number of steps per beat.

---

### 1.3 LENGTH

LENGTH defines the **total number of steps** in the pattern.
It is the **authoritative value** used by playback engines.

When TIME_SIG and GRID are both present, the expected LENGTH of a standard
2-bar ADT pattern is calculated as:

```
LENGTH = bars × beats_per_bar × steps_per_beat
```

Where:
- `bars` = 2 (ADT convention)
- `beats_per_bar` = numerator of TIME_SIG
- `steps_per_beat` = determined by GRID

#### Examples

| TIME_SIG | GRID | LENGTH |
|---------:|-----:|-------:|
| 4/4 | 16 | 32 |
| 3/4 | 16 | 24 |
| 3/4 | 8T | 18 |
| 4/4 | 8T | 24 |
| 5/4 | 16 | 40 |

---

### 1.4 GRID–LENGTH Example Table (4/4 only)

The following table applies **only to TIME_SIG=4/4** and is provided
for reference:

| GRID | LENGTH (2 bars, 4/4) |
|-----:|---------------------:|
| 16   | 32 |
| 8T   | 24 |
| 16T  | 48 |

---

## 2. Pattern Length Convention

ADT patterns are conventionally defined as **2 bars in length**.

The duration of a bar is determined by TIME_SIG.
Therefore, the absolute step count of a 2-bar pattern varies depending on
the time signature and grid resolution.

Patterns with non-32 step lengths (e.g. 18, 24, 36, 40) are valid and fully
supported.

---

## 3. Notes for Implementers

- Playback engines must rely on `LENGTH`, not `TIME_SIG`.
- Editors and converters are encouraged to validate LENGTH against
  TIME_SIG and GRID when present.
- If TIME_SIG is omitted, patterns may be interpreted as 4/4 for
  compatibility with legacy data.

---

## Appendix A — Changelog (v2.2a → v2.2b)

### What did NOT change
- File syntax and structure
- GRID values
- LENGTH semantics as total step count
- Playback behavior
- Backward compatibility

### What DID change

#### 1. TIME_SIG status clarified
- **v2.2a**: TIME_SIG described implicitly as informational
- **v2.2b**: TIME_SIG formally defined as musical metadata that may
  participate in LENGTH derivation and validation

#### 2. GRID–LENGTH relationship generalized
- **v2.2a**: GRID–LENGTH table implicitly assumed 4/4
- **v2.2b**: Table explicitly scoped to 4/4 examples only;
  general rule expressed as a formula

#### 3. “2-bar pattern” redefined
- **v2.2a**: Bar length implicitly fixed
- **v2.2b**: Bar duration explicitly determined by TIME_SIG

#### 4. Arbitrary meters explicitly supported
- **v2.2a**: Non-4/4 meters were structurally possible but undocumented
- **v2.2b**: Arbitrary time signatures are formally supported and documented

---

## Summary

ADT v2.2b is a **documentation-level clarification release** that formally
acknowledges what the format already allowed in practice:

> ADT is inherently meter-agnostic.  
> Time signature is musical metadata, not a structural limitation.
