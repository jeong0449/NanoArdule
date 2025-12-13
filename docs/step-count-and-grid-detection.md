# Step Count and Grid Detection in the Ardule Pattern System

This document explains how a single drum pattern is structured in terms of
**step count**, how **straight vs. triplet grids** are automatically detected,
and how users can explicitly override this decision when converting MIDI files
using `adc-mid2adt.py`.

---

## 1. Fundamental Assumptions

In the Ardule system, a drum pattern is defined with the following assumptions:

- A pattern spans **exactly two musical bars**
- Timing is quantized to a **fixed, uniform grid**
- All drum events are aligned to grid steps
- The pattern is tempo-independent once converted into ADT / ADP

These assumptions allow patterns to be compact, comparable, and efficiently
played back on resource-constrained hardware.

---

## 2. What Is a Step?

A **step** is the smallest discrete time unit used to represent rhythmic
positions in a pattern.

Each step may contain:
- No note (rest)
- One or more drum hits (collapsed into a single event per slot)

The total number of steps per pattern is determined by:
- The grid type (straight or triplet)
- The fixed pattern length (2 bars)

---

## 3. Canonical Step Counts

Ardule supports the following canonical step counts per **2-bar pattern**:

| Grid type | Musical subdivision | Steps per bar | Steps per 2 bars |
|----------|---------------------|---------------|------------------|
| Straight | 16th notes          | 16            | 32 |
| Triplet | 8th-note triplets   | 12            | 24 |
| Triplet | 16th-note triplets  | 24            | 48 |

These values are fixed and explicitly stored in ADT metadata.

---

## 4. Straight vs. Triplet Grids

### 4.1 Straight Grid

A **straight grid** divides each bar into equal 16th-note steps:

```
| 1 e & a | 2 e & a | 3 e & a | 4 e & a |
```

Characteristics:
- Common in rock, pop, funk, and electronic music
- Natural fit for most drum machines and DAWs
- Grid size: 16 steps per bar

---

### 4.2 Triplet Grid

A **triplet grid** divides beats into three equal parts:

```
| 1-trip-let | 2-trip-let | 3-trip-let | 4-trip-let |
```

Characteristics:
- Essential for swing, shuffle, jazz, and Latin feels
- Captures rhythmic intent not representable on a straight grid
- Grid sizes: 12 or 24 steps per bar

---

## 5. Automatic Grid Detection (`adc-mid2adt.py`)

By default, `adc-mid2adt.py` automatically detects whether a MIDI pattern
is best represented using a straight or triplet-based grid.

### 5.1 Detection Concept

The detection process analyzes **note-on event timing**:

1. Candidate grids (straight and triplet) are evaluated
2. Notes are projected onto each grid
3. Total quantization error is measured
4. The grid with the **lowest accumulated error** is selected

This approach preserves the rhythmic feel of the original performance
without relying on style labels or user hints.

---

### 5.2 Detection Result

Once detected:
- The grid type determines the **step count**
- The grid type is stored explicitly in the ADT header
- The grid becomes an **immutable property** of the pattern

---

## 6. User-Specified Grid Override

Although automatic detection is the default, users may explicitly
specify the grid type when running `adc-mid2adt.py`.

When a grid is forced by the user:

- Automatic detection is bypassed
- The specified grid and step count are used unconditionally
- All generated patterns share the same grid definition

This is useful when:
- MIDI timing is ambiguous
- Editorial consistency is required
- The user wants full control over rhythmic interpretation

> Refer to the built-in help (`-h / --help`) of `adc-mid2adt.py`
> for the exact command-line options.

---

## 7. Design Rationale

Automatic grid detection preserves musical intent,
while user override ensures reproducibility and control.

This dual mechanism reflects a core Ardule principle:

> *Automation by default, explicit control when needed.*

---

## 8. Summary

- A single Ardule pattern always spans **two bars**
- Step count is fixed by the selected grid
- Straight and triplet grids represent distinct rhythmic spaces
- `adc-mid2adt.py` detects the grid automatically by default
- Users may override the grid selection explicitly
- The final grid choice becomes part of the pattern’s identity
