# ADP Specification
**Ardule Drum Pattern Binary Format (ADP)**

> **First published:** Original ADP v2.2 specification
>
> **Documentation revision:** 2026-07-21
>
> The binary header and payload layout in this document were verified
> against the APS reference implementation (`aps_core.py`).
> This revision documents the existing ADP v2.2 format only.
> **No changes have been made to the binary file format itself.**

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

- An ADP file represents **exactly one drum pattern**
- The pattern consists of a fixed number of discrete playback steps
- In ADP v2.2, this corresponds to the complete pattern exported from an ADT file
- Timing is grid-based
- Playback is inherently looped

The musical time signature is intentionally **not** stored in ADP.
Playback engines interpret the pattern solely from the stored step count,
grid type, and timing parameters.

---

## 4. File Overview

An ADP file consists of:

1. File header
2. Pattern event data

All numeric values are stored in **little-endian** byte order.

---

## 5. File Header

The ADP v2.2 binary header consists of the following fields.

### 5.1 Binary Header Layout

The header size is fixed at **20 bytes**.

| Offset | Size | Field | Description |
|------:|----:|-------|-------------|
|0x00|4|Magic|`ADP2`|
|0x04|1|Version|Format version (22 = v2.2)|
|0x05|1|Grid Code|0=16, 1=8T, 2=16T|
|0x06|1|Length|Pattern length in **steps**|
|0x07|1|Slots|Number of drum slots|
|0x08|2|PPQN|Pulses per quarter note|
|0x0A|1|Swing|Playback parameter (currently unused)|
|0x0B|2|Tempo|Optional tempo field|
|0x0D|1|Reserved|Reserved for future expansion|
|0x0E|2|ADT CRC|CRC of the source ADT|
|0x10|4|Payload Bytes|Length of event payload in bytes|

### 5.2 Header Notes

- All numeric values are little-endian.
- `Length` stores the total number of playback steps, not bars.
- ADP intentionally does **not** store the musical time signature.
- The header completely defines how the payload is decoded.

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

### 6.3 Payload Structure

For each playback step:

1. One byte stores the number of hits.
2. The corresponding packed hit bytes immediately follow.

### 6.4 Packed Hit Byte

Each hit occupies one byte.

| Bits | Meaning |
|------|---------|
|7–6|Reserved|
|5–2|Slot index (0–15)|
|1–0|Accent level (0–3)|

### 6.5 Slot Interpretation

> **Note — Drum Slot Interpretation**
>
> ADP stores only **slot indices** and **accent levels** for each drum event.
>
> The percussion instrument assigned to each slot is **not stored** in the ADP file.
>
> Therefore, an ADP playback engine assumes that both the encoder and the decoder share the same predefined slot ordering.
>
> The ADP specification intentionally does **not** define which percussion instrument corresponds to each slot.
> The slot assignment is determined by the authoring environment and the playback implementation.
>
> Current ADP implementations assume the following default slot ordering:
>
> | Slot | MIDI Note | Instrument |
> |-----:|----------:|------------|
> | 0 | 36 | Kick |
> | 1 | 38 | Snare |
> | 2 | 42 | Closed Hi-Hat |
> | 3 | 46 | Open Hi-Hat |
> | 4 | 45 | Low Tom |
> | 5 | 47 | Mid Tom |
> | 6 | 50 | High Tom |
> | 7 | 51 | Ride Cymbal |
> | 8 | 49 | Crash Cymbal |
> | 9 | 37 | Rim Shot |
> | 10 | 39 | Hand Clap |
> | 11 | 44 | Pedal Hi-Hat |
>
> This ordering reflects the current implementation and is not yet defined as a formal part of the ADP specification.
> Future versions of the ecosystem may standardize this ordering explicitly while preserving the ADP binary format.

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

ADP playback engines MUST NOT assume any specific time signature.

ADP **does not define tempo changes**.

---

## 9. What ADP Does NOT Define

ADP intentionally excludes:

- Tempo ownership
- Song structure
- Pattern chaining
- Explicit time signature definitions
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
