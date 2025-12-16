# ADP Specification  
**Ardule Drum Pattern Binary Format (ADP)**

## 1. Introduction

ADP (Ardule Drum Pattern) is a **binary pattern cache format** used in the Nano Ardule ecosystem.  
It represents a **fixed-length drum pattern** optimized for fast loading and deterministic playback on resource-constrained devices.

ADP is **not a streaming format** and must be clearly distinguished from ADS (Ardule Drum Stream).

Relationship between formats:

- **ADT**: Human-editable text pattern (authoring format)
- **ADP**: Binary cache of a single pattern (playback format)
- **ADS**: Time-ordered event stream (song / sequence format)

---

## 2. Design Goals

ADP is designed with the following goals:

- Fast loading from SD card
- Minimal memory footprint
- Deterministic timing during playback
- Simple decoding on microcontrollers
- One-to-one semantic correspondence with ADT

Non-goals:

- Streaming playback
- Arbitrary-length sequences
- Embedded tempo automation

---

## 3. Pattern Model

- An ADP file represents **exactly one pattern**
- Pattern length is **fixed (2 bars)**
- Timing is grid-based
- Playback is inherently looped

The pattern identity and length are intrinsic properties of ADP.

---

## 4. File Overview

An ADP file consists of:

1. File header
2. Pattern event data

All numeric values are stored in **little-endian** byte order.

---

## 5. File Header

The header defines global properties of the pattern.

Typical fields include:

- Magic identifier (`ADP`)
- Format version
- Grid code
- Pattern length (bars)
- Number of slots (instruments)
- PPQ (pulses per quarter note)
- Reserved bytes for future use

The header fully describes how the event data must be interpreted.

---

## 6. Event Encoding Model

### 6.1 Step-Based Encoding

- The pattern is divided into discrete **steps**
- Each step corresponds to a fixed tick interval
- Steps are processed sequentially and looped

### 6.2 Hit Encoding

For each step:

1. Hit count is stored
2. Each hit is encoded as a packed byte

### 6.3 Packed Hit Byte

A packed hit byte encodes:

- Slot index (instrument)
- Accent (velocity level)

Typical layout:

- Lower bits: slot index
- Upper bits: accent level (acc)

Exact bit allocation is implementation-defined but consistent across tools.

---

## 7. Velocity Levels

ADP uses four discrete velocity (accent) levels:

| acc | Meaning  | ADT Symbol |
|----:|----------|------------|
| 0   | Rest     | `.`        |
| 1   | Soft     | `-`        |
| 2   | Medium   | `x` / `X`  |
| 3   | Strong   | `o` / `O`  |

- ADP stores **numeric acc values (0–3)**
- Symbol mapping is defined in ADT v2.2a
- MIDI velocity interpretation is implementation-specific

> **Note — Velocity Representation in ADP v2.x**
>
> ADP v2.x does **not** store MIDI velocity values directly.
> Each drum hit is encoded using a 2-bit **accent level** (0–3),
> derived from ADT velocity symbols (`.`, `-`, `x`, `o`).
>
> During playback, the Nano Ardule (ADS) engine maps each accent level
> to an engine-defined **representative MIDI velocity**.
>
> **Recommended default mapping:**
>
> - Level 0 (`.`): rest → velocity **0**
> - Level 1 (`-`): soft / ghost → velocity **32**
> - Level 2 (`x`): medium / normal → velocity **80**
> - Level 3 (`o`): strong / accent → velocity **120**
>
> This design intentionally separates **rhythmic structure and emphasis**
> from **sound rendering**, allowing different engines or kits to apply
> their own dynamic response while preserving musical intent.


---

## 8. Playback Semantics

- ADP playback always loops
- No end-of-pattern event exists
- Timing is derived from:
  - Grid code
  - PPQ
  - External BPM

ADP **does not define tempo changes**.

---

## 9. What ADP Does NOT Define

ADP intentionally excludes:

- Tempo ownership
- Song structure
- Pattern chaining
- Time signatures beyond grid semantics
- Real-time control changes

These concerns are handled by higher-level formats (ARR, ADS) or runtime configuration.

---

## 10. Compatibility and Versioning

- ADP files include an explicit version field
- Parsers MUST reject unsupported major versions
- Minor version extensions SHOULD preserve backward compatibility

---

## 11. Design Rationale

ADP exists to provide:

- A stable, minimal binary representation of a drum pattern
- A clean boundary between pattern data and song sequencing
- Predictable behavior on embedded systems

By keeping ADP strictly pattern-centric, the Nano Ardule ecosystem remains modular and extensible.

---

## 12. License

This specification is released under the same license as the Nano Ardule project repository.
