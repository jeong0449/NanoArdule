# APS (Ardule Pattern Studio) – Key Map & Controls

**Last updated:** 2026-01-03

This document summarizes the current key bindings of **APS**,
with a focus on **Chain Edit** and related workflows.

---

## Global Keys

| Key | Action |
|-----|--------|
| `Q` | Quit APS |
| `H` | Show help |
| `Space` | Play / Stop |
| `C` | Cycle pattern suffix: P→B→H→P (H adds PLAY_BARS=1) |
| `S` | Enter Step Sequencer |
| `B` | Build hybrid pattern |
| `R` / `r` | Toggle repeat mode *(non-Chain focus only)* |

---

## Chain Edit Mode

Chain Edit is used to edit the linear, non-looping pattern timeline.

### Navigation

| Key | Action |
|-----|--------|
| `↑ / ↓` | Move cursor |
| `J / K` | Move cursor (vi-style) |
| `Enter` | Confirm / apply |
| `Esc / Q` | Cancel / exit dialog |

---

### Block Selection

| Key | Action |
|-----|--------|
| `V` | Mark block start (set anchor) |
| *(cursor movement)* | Extend block selection |

> `V` defines the **starting point** of a block in the pattern chain.
> Moving the cursor extends the block from this anchor.
> Block selection is shown using **reverse video** (highlight).

---

### Block Editing (Chain Edit only)

| Key | Action |
|-----|--------|
| `Y` | Yank (copy) selected block |
| `X` | Cut selected block |
| `P` | Paste block or section |
| `F` | Flush clipboard (clear) |
| `R` / `r` | Remove section at cursor *(Chain focus only)* |


Notes:
- `R`/`r` is **focus-aware**:
  - In **Chain focus**: removes the section at the current cursor line.
  - Outside Chain focus: toggles **repeat mode**.
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

_Last updated: 2026-01-03_


## List Focus–Specific Insert Keys

When the **file list** has focus (Patterns or ARR):

| Key | List Focus | Action |
|----|------------|--------|
| `Enter` | ARR list | Insert selected ARR **after** current chain cursor |
| `O` / `o` | ARR list | Insert selected ARR **before** current chain cursor |
| `Enter` | Patterns list | Insert selected pattern **after** cursor (or increase repeats) |
| `O` / `o` | Patterns list | Insert selected pattern **before** cursor |

Notes:
- `O` / `o` always means **insert-before** relative to the current chain cursor.
- Section split (`_L` / `_R`) and ARR section import (`i_` prefix) are applied automatically.
