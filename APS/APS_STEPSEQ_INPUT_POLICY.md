# APS StepSeq Input Policy (v3.0a)

Version: 3.0a  
Stabilized: 2026-03-02  
Applies to: aps_stepseq.py (v3.0a and later)  
Scope: Keyboard input behavior and destructive safety model  

---

## 1. Design Principles

StepSeq input behavior follows these core principles:

1. Conflict-free key mapping
2. Minimal modifier usage
3. Destructive actions require deliberate keys
4. Undo must be predictable and musically intuitive
5. Loop is always active
6. Input policy must not alter structural architecture  
   (no change to stepseq_mode return or draw layout)

---

## 2. Navigation

| Action | Key |
|--------|-----|
| Move left | `h` |
| Move down | `j` |
| Move up | `k` |
| Move right | `l` |
| Previous bar | `[` |
| Next bar | `]` |

---

## 3. Recording Model

StepSeq uses a 3-stage recording state:

- **STBY** – standby
- **ARMED** – armed but not yet recording
- **REC** – recording enabled

### Record Arm

- `r` → Toggle record arm

Uppercase `R` is intentionally not used to avoid destructive conflicts.

---

## 4. Loop Behavior

Loop is always active.

`O` toggles loop scope:

- `BAR`
- `PATTERN`

There is no ON/OFF concept.

---

## 5. Destructive Operations (Official)

Destructive operations are bound to function keys
to reduce accidental activation.

| Action | Key |
|--------|------|
| Delete row | `F7` |
| Delete column | `F8` |
| Delete bar | `F9` |

Legacy Shift+B/R/C bindings were removed in v3.0a.

---

## 6. Stamp (Step Input)

- `Enter` performs stamp.
- Stamp is allowed only when:
  - Recording state = REC
  - Not in count-in phase

STOP state is preview-only.

---

## 7. Undo Model

Undo is single-level and pattern-scoped.

### Keys

- `Ctrl + Z`
- `Backspace`
- `Delete`

All perform identical undo.

---

### Undo Scope

Undo reverts:

- The most recent destructive action
- The most recent stamp
- Or an entire REC take

---

### Take-Level Undo (Introduced in v3.0a)

When recording begins:

- A full pattern snapshot is stored.
- After STOP, `Ctrl+Z` rolls back the entire take.

Example:

1. Clear bar (F9)
2. Record 4 kick hits
3. STOP
4. Ctrl+Z

Result:
- The 4 recorded kicks are removed.
- The cleared bar remains cleared.

---

## 8. Removed Concepts (v3.0a Cleanup)

- “Clear last hit-group” removed
- Shift-based destructive commands removed
- Loop ON/OFF removed
- Ambiguous Record/Row key conflicts resolved

---

## 9. Stability Guarantee

This document defines the official input behavior
for StepSeq v3.0a as of 2026-03-02.

Future modifications must update this document
before implementation.
