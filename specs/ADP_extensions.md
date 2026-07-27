# ADP Extensions
**Initial version:** 2026-07-27

---

# 1. Purpose

The ADP binary format is intended to remain stable over time.
New features should be introduced through backward-compatible
extension mechanisms whenever possible.

This document defines the currently supported extension methods.

---

# 2. Design Principles

- Do not modify the core ADP binary layout.
- Preserve backward compatibility.
- Extensions shall remain optional.
- Players that do not support an extension shall still be able to play the pattern.

---

# 3. Instrument Set Extension

## 3.1 Overview

ADP supports multiple percussion layouts while preserving a fixed
slot count.

The Instrument Set ID is stored in the ADP header.

| Offset | Size | Field |
|-------:|----:|-------|
|0x0D|1|Instrument Set ID|

## 3.2 Defined IDs

| ID | Name |
|--:|------|
|0|Legacy UI 12|
|1|APS Default 12|

Other values are reserved.

Players shall select the appropriate slot-to-instrument mapping
according to this value.

---

# 4. Flam Sidecar Extension

## 4.1 Overview

Flam information is intentionally kept outside the ADP binary.

A matching sidecar file may accompany an ADP file.

Example:

```
rock01.adp
rock01.flm
```

The absence of a sidecar file shall not affect normal playback.

---

## 4.2 Player Behavior

When loading an ADP pattern, the player should:

1. Load the ADP file.
2. Search for a matching `.flm` file.
3. If found, load flam events.
4. Merge flam events during playback.

If no sidecar exists, playback proceeds normally.

---

## 4.3 Compiler Behavior

An ADT compiler may generate both:

```
rock01.adp
rock01.flm
```

from a single ADT source.

---

## 4.4 File Format

The FLM sidecar is a compact binary file.

Its detailed binary structure is intentionally left open for future
revision.

---

# 5. Compatibility

Extensions defined in this document are optional.

Players that do not recognize an extension shall ignore it whenever
possible and continue normal playback.

---

# 6. Future Extensions

Examples of future extensions include:

- Additional Instrument Set IDs
- Humanization metadata
- Ornament sidecars
- Other backward-compatible playback enhancements

The ADP binary format itself should remain unchanged whenever practical.
