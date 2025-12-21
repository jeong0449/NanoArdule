# APS (Ardule Pattern Studio) – Key Map & Controls

This document summarizes the current key bindings of **APS**,
with a focus on **Chain Edit** and related workflows.

---

## Global Keys

| Key | Action |
|----|-------|
| `Q` | Quit APS |
| `H` | Show help |
| `Space` | Play / Stop |
| `C` | Instant pattern copy (global) |
| `S` | Enter Step Sequencer |
| `B` | Build hybrid pattern |

---

## Chain Edit Mode

Chain Edit is used to edit the linear, non-looping pattern timeline.

### Navigation

| Key | Action |
|----|-------|
| `↑ / ↓` | Move cursor |
| `J / K` | Move cursor (vi-style) |
| `Enter` | Confirm / apply |
| `Esc / Q` | Cancel / exit dialog |

---

### Block Selection

| Key | Action |
|----|-------|
| `V` | Mark block start (set anchor) |
| *(cursor movement)* | Extend block selection |

> `V` defines the **starting point** of a block in the pattern chain.
> Moving the cursor extends the block from this anchor.
> Block selection is shown using **reverse video** (highlight).

---

### Block Editing (Chain Edit only)

| Key | Action |
|----|-------|
| `Y` | Yank (copy) selected block |
| `X` | Cut selected block |
| `P` | Paste block or section |
| `F` | Flush clipboard (clear) |

Notes:
- `Y` copies the selected block and clears the highlight.
- `X` cuts the block and updates the chain immediately.
- `P` opens a dialog to choose from:
  - Clipboard contents
  - Named sections
- `F` clears the clipboard without affecting the chain.

---

## Paste Dialog

When pressing `P` in Chain Edit:

- A dialog titled **“Paste: choose block”** appears.
- Available sources:
  - `[Clipboard]` – last yanked/cut block
  - `[Section]` – predefined chain sections
- Use `↑ / ↓` to select, `Enter` to paste, `Esc` to cancel.

If labels are long and truncated in the list,
a preview area may show the full label below.

---

## Visual Conventions

- **Reverse video**: block selection only
- **Bold / color**: current cursor line
- Clipboard state is shown via status messages

---

## Design Principles

- The main chain is a **linear time axis** (no implicit loops).
- Sections are **metadata**, not structural flow control.
- Clipboard is an explicit, user-managed state.
- Editing commands are mode-specific to avoid key conflicts.

---

_Last updated: APS v0.27_
