# StepSeq Variable Grid Support Plan

## Background

Historically, the APS StepSeq (step sequencer) subsystem was designed with a **fixed 32-step grid** assumption. This reflected the most common drum-pattern use case at the time:

- 4/4 time
- Straight 16th-note grid
- 2 bars × 16 steps = **32 steps**

Under this assumption, many parts of the StepSeq implementation were hard-coded around a 32-step structure (e.g., two 16-step pages, fixed copy operations, and fixed cursor logic).

As a result, **patterns with LENGTH=24 were explicitly or implicitly rejected** by StepSeq, even though such patterns are musically valid.

This document explains the original rationale for that policy and outlines the plan to evolve StepSeq toward a **fully variable grid-length architecture** aligned with the ADT specification.

---

## ADT Grid and Length Specification (Authoritative)

The ADT specification defines grid type and length as a coupled pair:

| GRID | Meaning | LENGTH |
|------|---------|--------|
| 16   | Straight 16th-note grid | 32 |
| 8T   | 8th-note triplet grid   | 24 |
| 16T  | 16th-note triplet grid  | 48 |

Therefore:
- **LENGTH=24 is not an exception** or a special-case blues hack
- It is the **canonical representation of an 8th-note triplet (shuffle / blues) grid**

Any editor or player that claims ADT compliance must eventually support these combinations.

---

## Why StepSeq Previously Rejected LENGTH=24

The historical restriction was not a musical decision, but an **engineering safety constraint**. Key limitations included:

1. **Fixed step count (32)**
   - Internal step grids were always created with 32 cells, regardless of pattern metadata

2. **Two-page UI model**
   - Page 0: steps 0–15
   - Page 1: steps 16–31
   - No concept of variable page count

3. **Hard-coded copy semantics**
   - Copy operations assumed `0–15 → 16–31`
   - This is invalid for 24-step (12+12) or 48-step (24+24) patterns

4. **Index safety**
   - Allowing LENGTH=24 without refactoring would lead to out-of-range access or semantically incorrect edits

For these reasons, StepSeq deliberately limited itself to LENGTH=32 to avoid subtle corruption or crashes.

---

## Design Goal Going Forward

The goal is to evolve StepSeq into a **grid-aware, length-agnostic editor** that correctly supports all valid ADT grid/length pairs:

- 32 steps (GRID=16)
- 24 steps (GRID=8T)
- 48 steps (GRID=16T)

This will ensure:
- Full ADT specification compliance
- Correct handling of triplet-based patterns (shuffle, blues, swing)
- Long-term extensibility beyond a single fixed grid

---

## Planned Architectural Changes

### 1. Variable Step Count

- Replace hard-coded `steps = 32` with:
  ```text
  steps = pattern.length
  ```

### 2. Generalized Paging Model

- Define:
  ```text
  page_size = 16
  pages = ceil(steps / page_size)
  ```
- Cursor movement and page switching will operate over `pages` instead of assuming exactly two pages

### 3. Grid-Aware Copy and Edit Operations

- Derive bar length dynamically:
  ```text
  bar_steps = steps / bars
  ```
- Copy operations will be defined as:
  ```text
  first_bar → second_bar
  ```
  rather than fixed index ranges

### 4. UI Rendering Adjustments

- Rendering loops will clamp to `steps`
- No access beyond valid step indices
- Partial pages (e.g., last 8 steps of a 24-step pattern) will be rendered safely

---

## Transitional Policy

Until the above refactoring is complete:

- StepSeq may continue to **restrict editing to 32-step patterns only**
- Patterns with LENGTH=24 or 48 remain fully supported by:
  - APS playback
  - ARR chaining
  - ADS streaming to embedded Ardule Player

This avoids data corruption while preserving musical correctness at the engine level.

---

## Summary

- LENGTH=24 patterns are **fully valid** under the ADT specification
- Historical rejection in StepSeq was a **temporary engineering constraint**, not a conceptual limitation
- StepSeq will be refactored to support **variable grid lengths** in a principled, grid-aware manner

This change aligns StepSeq with the long-term goals of the Ardule / APS ecosystem: clarity, correctness, and extensibility.

