# APS Key Map (Ardule Pattern Studio)

Last update: **2026-02-03**

---

## Global Keys

| Key | Action |
|-----|--------|
| `q` / `F10` | Quit APS |
| `Space` | Play / Stop |
| `H` / `F1` | Help |

---

## Function Keys

| Key | Action |
|-----|--------|
| `F1` | Help |
| `F2` | Toggle left list: **Pattern / Arrangement** |
| `F3` | Refresh (rescan patterns / ARR; keeps filters) |
| `F4` | Info (show ADT / ARR details) |
| `F5` | Duplicate Pattern |
| `F6` | MIDI settings |
| `F7` | Save ARR |
| `F8` | Count-in settings |
| `F9` | BPM |
| `q` / `F10` | Quit APS |

---

## Navigation (Common)

| Key | Action |
|-----|--------|
| `↑ / ↓` | Move cursor |
| `J / K` | Move cursor (vi-style) |
| `Enter` | Confirm / Apply |
| `Esc` | Cancel / Exit dialog |

---

## List / Browser

| Key | Action |
|-----|--------|
| `G` | Genre filter (Pattern list) |
| `PgUp / PgDn` | Fast scroll |
| `C` | Cycle pattern suffix (`P → B → h → P`) |

---

## Chain Edit – Block Selection

| Key | Action |
|-----|--------|
| `V` | Set block start (anchor) |
| *(move cursor)* | Extend block selection |

Block selection is shown using reverse video.

---

## Chain Edit – Block Operations

| Key | Action |
|-----|--------|
| `Y` | Yank (copy block) |
| `X` | Cut block |
| `P` | Paste (clipboard / section) |
| `F` | Flush clipboard |

---

## Chain Edit – Section Labels

| Key | Action |
|-----|--------|
| `S` | Attach section label at cursor |
| `R` | Remove section label at cursor |

Notes:
- Section labels are **metadata only** and do not affect playback order.
- `S` opens a prompt to enter or select a section name.
- `R` removes the section label at the current chain position.
- In non-Chain focus, `R` keeps its original meaning.


---

## Chain Edit – Pattern Editing

| Key | Action |
|-----|--------|
| `Enter` | Open StepSeq for the pattern at cursor |

---

## Insert (Focus-aware)

| Focus | Key | Action |
|-------|-----|--------|
| ARR list | `Enter` | Insert after cursor |
| ARR list | `O / o` | Insert before cursor |
| Pattern list | `Enter` | Insert / increase repeat |
| Pattern list | `O / o` | Insert before cursor |

---

## Step Sequencer (StepSeq)

- Supported grids:
  - **32-step** (straight)
  - **24-step** (8T triplet)
  - **48-step** (16T triplet)
- Half pattern (`_h`):
  - `PLAY_BARS = 1`
  - Second bar is visually disabled but editable
- Bar separators are explicitly shown

### Bar Playback Range Selection

In Step Sequencer, pressing `L` cycles the playback range of the current pattern
in the following order:

- **1st bar** → **2nd bar** → **Full bar**

This selection affects playback only and does not modify pattern data.
It is useful for focusing on a specific bar while editing or auditioning
rhythmic details.


---

## Design Notes (Mental Model)

- **ADT** = Pattern (reusable rhythmic unit)
- **ARR** = Arrangement (ordered structure of patterns)
- Chain represents a **linear time axis**
- Sections are **labels only**
- Bar counts and positions are **computed**, not stored
