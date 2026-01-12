# ADS Specification (Ardule Data Stream)

**Last update: January 12, 2026**

---

## ADS v0.1

### 1. Purpose

This document defines **ADS v0.1 (Ardule Data Stream)**, the final executable
time representation used by the Ardule firmware.

ADS is **not a musical score format** and **not an editing format**.
It is the *result* of interpreting higher-level musical intent (ADT / ARR)
under the **MetaTime principle**, producing a deterministic, linear event stream.

Once data is encoded as ADS, **all musical interpretation is finished**.

---

### 2. The MetaTime Principle

#### Core statement

> **Machines do not know time signatures.**

For firmware, musical time is fully determined by:

- Event order
- Event spacing (tick distance)
- Total playback length

Concepts such as bars, meters, or time signatures exist **only as metadata**
for humans and authoring tools.

#### Consequences

- Time is **calculated**, not described.
- Playback logic must never branch on “3/4 vs 4/4”.
- ADS contains **no bar, meter, or grid information**.
- Firmware acts only as a time executor.

---

### 3. Time Hierarchy in the Ardule System

```
ADT (pattern description)
   |
   |  MetaTime interpretation
   v
ARR (structural intent, ordering, metadata)
   |
   |  Time calculation
   v
ADS (absolute event stream)
```

#### Responsibilities

| Layer | Responsibility |
|------|----------------|
| ADT  | Step data, grid resolution, local intent |
| ARR  | Ordering, repetition, tempo context, metadata |
| ADS  | Absolute time result (ticks + events) |
| FW   | Playback only (no musical interpretation) |

---

### 4. ADS Design Goals

ADS v0.1 is designed to be:

- **Minimal** – no musical semantics
- **Deterministic** – same input always yields same playback
- **Firmware-friendly** – sequential, streamable binary format
- **Context-free** – fully playable without ADT/ARR references

---

### 5. Count-In as a Meta Prelude

#### Definition

A count-in is **not musical data**.
It is a *temporal prelude* intended only to assist human performers.

In ADS, count-in events are treated exactly like normal events,
but their origin is **internal generation**, not pattern data.

#### Rules

- No pattern files are used for count-in
- Count-in is measured in **beats**, not bars
- Beat = TIME_SIG denominator note (metadata only)
- Count-in events may use a **tick offset (tick ≥ 1)**

#### Priority order

1. CLI override (`--countin N`)
2. ARR metadata (`#COUNTIN`)
3. Default: OFF

---

### 6. ADS v0.1 Binary Format

#### Overview

ADS is a binary stream consisting of:

1. A fixed-size header
2. A sequence of fixed-size event records

All multi-byte fields are **little-endian**.

---

#### 6.1 Header Layout

| Field | Size | Description |
|------|------|-------------|
| Magic | 4 B | ASCII `ADS0` |
| BPM | 2 B | Final tempo (integer BPM) |
| PPQ | 2 B | Ticks per quarter note |
| Drum CH | 1 B | MIDI channel (0-based) |
| Event count | 4 B | Number of event records |

**Total header size: 13 bytes**

---

#### 6.2 Event Record Layout

Each event record is exactly **8 bytes**:

| Field | Size | Description |
|------|------|-------------|
| Tick | 4 B | Absolute tick position |
| Kind | 1 B | `1` = note-on, `0` = note-off |
| Note | 1 B | MIDI note number |
| Velocity | 1 B | Velocity (0 for note-off) |
| Reserved | 1 B | Must be `0` |

---

### 7. Design Invariants

- ADS is linear and absolute
- Time is never inferred
- All interpretation happens before ADS generation
- Firmware executes; it does not decide

---

### 8. Closing Statement

MetaTime is not an optimization.

It is a **boundary**.

Once musical intent has been reduced to absolute ticks,
everything beyond ADS is execution.
