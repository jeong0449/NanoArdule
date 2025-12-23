# ARR v0.1 Specification  
**Ardule Arrangement File Format (ARR)**

This document defines **ARR v0.1**, a text-based domain-specific language (DSL) for describing the structural arrangement of drum patterns in the Nano Ardule ecosystem.

---

## 1. Introduction

ARR (Ardule Arrangement) describes **how patterns are ordered and repeated**, but does **not** define playback timing itself.

ARR files are **compiled into ADS (Ardule Drum Stream)**, which is the actual streaming format consumed by the Nano Ardule player.

Relationship between formats:

- **ADT**: Human-editable drum pattern (2-bar, text)
- **ADP**: Binary cache of a single pattern
- **ARR**: Pattern arrangement / structure description (this document)
- **ADS**: Time-ordered event stream (playback format)

---

## 2. Design Goals

ARR v0.1 is intentionally minimal but expressive.

Goals:
- Human-readable, text-editor friendly
- Friendly to version control (diff/merge)
- Explicit support for 1-bar and 2-bar usage
- Clear separation between *structure* and *playback*
- Deterministic compilation into ADS

Non-goals:
- Direct playback
- Real-time control
- Conditional branching
- Tempo automation

---

## 3. File Encoding and Layout

- Encoding: UTF-8
- Line-based syntax
- Empty lines are ignored
- Lines starting with `#` are comments
- Inline comments are not supported in v0.1

---

## 4. BPM Hint

An ARR file MAY specify a **BPM hint** at the beginning of the file.

Syntax:
```text
BPM <number>
```

Rules:
- BPM hint MUST appear before any section or flow definition
- BPM hint is informational only
- Actual playback tempo is determined by the runtime environment
- ADS compilation MAY store this value as metadata

---

## 5. Pattern Items

### 5.1 Pattern Name

```
NAME
```

- `NAME` refers to a pattern base name
- `.ADP` is preferred; `.ADT` MAY be used if ADP is unavailable
- Absence of modifiers implies full 2-bar usage

---

### 5.2 Half-Pattern Selection

ARR allows explicit selection of which bar of a 2-bar pattern to use.

Syntax:
```
NAME@A   # first bar only
NAME@B   # second bar only
```

Rules:
- `@A` selects the first bar
- `@B` selects the second bar

---

### 5.3 Repetition

Any pattern item MAY be repeated.

Syntax:
```
ITEM*N
```

Where `N` is an integer ≥ 1.

---

## 6. Grouping

Multiple items MAY be grouped and repeated as a unit.

Syntax:
```text
(
  ITEM
  ITEM
)*N
```

Rules:
- `(` and `)` MUST appear on their own lines
- `*N` applies to the entire group
- Nested groups are not allowed in v0.1

---

## 7. Section Definitions

ARR v0.1 supports **explicit section definitions** at the top of the file.

### 7.1 Section Definition Syntax

```
[SECTION_NAME]:
  ITEM
  ITEM
```

Rules:
- Section definitions MUST appear before the play flow
- Section names MUST be unique
- Section bodies consist of pattern items and/or groups

Example:
```text
[VERSE]:
RCK_P010*2
RCK_P011*2
```

---

## 8. Play Flow Definition

After section definitions, ARR defines a **play flow**, which specifies the actual playback order.

### 8.1 Play Flow Syntax

The play flow is introduced by a dedicated section header:

```text
[PLAY]:
```

The body of `[PLAY]:` consists of:
- Section names (referencing previously defined sections)
- Direct pattern items (one-shot patterns)
- Groups

Example:
```text
[PLAY]:
INTRO
VERSE
RCK_FILL_003@1
CHORUS
```

Rules:
- `[PLAY]:` MUST appear exactly once
- Items are processed sequentially
- Section references are expanded inline during compilation

---

## 9. Compilation Semantics

ARR compilation proceeds as follows:

1. Parse BPM hint (if present)
2. Parse section definitions
3. Parse play flow
4. Expand section references
5. Expand repetitions and groups
6. Resolve pattern references
7. Apply bar selection (`@1` / `@2`) and rebase timing
8. Emit a linear ADS event stream

---

## 10. Error Handling

The compiler MUST fail if:

- A referenced section is undefined
- A referenced pattern file does not exist
- `@` specifier is not `@1` or `@2`
- Repetition count is invalid
- Group syntax is malformed
- `[PLAY]:` section is missing or duplicated

Error messages SHOULD include line numbers.

---

## 11. Versioning

This document defines **ARR v0.1**.

- Future versions MAY extend syntax
- v0.1 parsers MUST reject unsupported future major versions
- Backward compatibility SHOULD be preserved where possible

---

## 12. Complete Example

```text
# Nano Ardule ARR v0.1 example

BPM 118

[INTRO]:
RCK_P001@1*2

[VERSE]:
RCK_P001*2
RCK_P002*2

[CHORUS]:
(
  RCK_P003
  RCK_P003@2
)*2

[PLAY]:
INTRO
VERSE
CHORUS
RCK_FILL_004@1
CHORUS
```

---

## 13. License

This specification is released under the same license as the Nano Ardule project.
