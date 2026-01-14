# APS Structure Map (v0.05 era)

**Last updated:** 2026-01-14

This document describes the **current structure of APS (Ardule Pattern Studio)**,
based on the existing source files.  
It focuses on **module responsibilities and data flow**, excluding any future refactoring plans.

---

## 1. Overall Architecture

APS is organized around a **central TUI controller** with clearly separated
UI, editor, domain-logic, and tool modules.

```
+-----------------------------------------------------------+
|                       aps_main (TUI entry)                |
|  - curses main loop / mode switching / key dispatch        |
|  - file dialogs / load-save orchestration                  |
|  - "what to do when user presses a key"                    |
+--------------------------+----------------------+----------+
                           |                      |
                           v                      v
+--------------------------+      +--------------------------+
|          aps_ui          |      |      Domain modules      |
|  - NC dialogs            |      |  (parsing / logic)       |
|  - windows / layout      |      |  - aps_arr               |
|  - drawing helpers       |      |  - aps_sections          |
+--------------------------+      |  - aps_countin           |
                                  |  - aps_core              |
                                  |  - aps_playback          |
                                  +------------+-------------+
                                               |
                                               v
                                  +--------------------------+
                                  |       Editors / Modes    |
                                  |  - aps_stepseq           |
                                  |  - aps_chainedit         |
                                  |                          |
                                  |  (uses core + playback + |
                                  |   section data + ARR)    |
                                  +--------------------------+
```

---

## 2. File-Level Responsibility Map

### Entry Point / Orchestrator

**aps_main.py**
- curses-based main event loop
- global screen redraw and focus handling
- key dispatch and mode switching
- orchestration of load/save flows
- ARR write logic (including `BARS|` serialization)
- integration point for all editors and playback

---

### UI Toolkit (Reusable)

**aps_ui.py**
- Norton Commander style dialogs (alert, input, confirm)
- window creation and layout helpers
- reusable drawing utilities
- visual consistency across all APS modes

---

### Editors (Interactive Modes)

**aps_stepseq.py**
- ADT step sequencer editor
- grid rendering and cursor movement
- view window / visible-bar selection
- velocity/accent manipulation
- pattern-level save workflow

**aps_chainedit.py**
- ARR chain editor
- pattern insertion, deletion, duplication, repetition
- block selection and chain-level edit operations
- section-aware editing
- per-entry bar selection (F/A/B) interaction layer

---

### Domain / Data Logic

**aps_arr.py**
- ARR file parsing and loading
- pattern pool and fully expanded `MAIN|` sequence parsing
- per-entry bar selection (`BARS|`) parsing and serialization
- `#SECTION` handling (ARR 1-based → internal 0-based conversion)
- provides structured ARR data to editors and playback

**aps_sections.py**
- section data structures and utilities
- section validation and ordering
- helpers for section-aware display and logic

**aps_countin.py**
- count-in metadata definitions
- count-in mode handling for playback

**aps_core.py**
- shared core data structures (e.g., `ChainEntry`)
- semantic fields for chain entries (`repeats`, `bars`)
- play-length computation logic (full vs half, A/B selection)
- lightweight utilities reused across modules

**aps_playback.py**
- playback engine
- timing and sequencing logic
- MIDI output coordination
- interaction with count-in and chain data

---

### Toolchain (External Utilities)

**adc_adt2adp.py**
- ADT → ADP conversion tool
- binary cache generation
- part of the APS toolchain, not the interactive TUI

---

## 3. Data Flow Overview

### A. Pattern Editing Flow (ADT / ADP)

```
ADT file
  → aps_stepseq (edit, grid, save)
      → adc_adt2adp (optional ADP generation)
```

---

### B. Chain / ARR Editing and Playback Flow

```
ARR file
  → aps_arr.parse_arr (including per-entry BARS|)
      → aps_main (state construction, bars preserved)
          → aps_chainedit (editing)
          → aps_playback (playback)
```

ARR saving:
```
aps_main
  → rewrite ARR with header and metadata
  → write #SECTION (1-based)
  → generate #PLAY metadata
  → serialize BARS| when needed
```

---

### C. Section Metadata Flow

```
#SECTION (ARR file, 1-based)
  → aps_arr (convert to internal 0-based)
      → aps_sections utilities
      → UI display and #PLAY generation
```

Sections affect:
- chain visualization
- #PLAY metadata generation
- editor navigation logic

---

## 4. Current Design Characteristics

- Clear separation between UI, editors, and domain logic
- ARR format treated as a stable external specification (v0.05)
- Per-entry bar selection (`BARS|`) treated as authoritative chain semantics
- Internal representation remains 0-based for consistency
- #PLAY handled strictly as metadata (non-authoritative)
- Toolchain scripts kept independent from interactive TUI

---

*This document reflects the current stabilized APS architecture
after the introduction of per-entry bar semantics (BARS|).*