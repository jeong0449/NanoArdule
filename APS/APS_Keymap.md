# APS Key Map (Ardule Pattern Studio)

Last update: **2026-03-02 (StepSeq v3.0a aligned)**

------------------------------------------------------------------------

## Global Keys

  Key           Action
  ------------- -------------
  `q` / `F10`   Quit APS
  `Space`       Play / Stop
  `H` / `F1`    Help

------------------------------------------------------------------------

## Function Keys

  Key           Action
  ------------- ------------------------------------------------
  `F1`          Help
  `F2`          Toggle left list: **Pattern / Arrangement**
  `F3`          Refresh (rescan patterns / ARR; keeps filters)
  `F4`          Info (show ADT / ARR details)
  `F5`          Duplicate Pattern
  `F6`          MIDI settings
  `F7`          Save ARR *(StepSeq overrides)*
  `F8`          Count-in settings *(StepSeq overrides)*
  `F9`          BPM (30--240) *(StepSeq overrides)*
  `q` / `F10`   Quit APS

------------------------------------------------------------------------

## Navigation (Common)

  Key       Action
  --------- ------------------------
  `↑ / ↓`   Move cursor
  `J / K`   Move cursor (vi-style)
  `Enter`   Confirm / Apply
  `Esc`     Cancel / Exit dialog

------------------------------------------------------------------------

## List / Browser

  Key             Action
  --------------- ----------------------------------------
  `G`             Genre filter (Pattern list)
  `PgUp / PgDn`   Fast scroll
  `C`             Cycle pattern suffix (`P → B → h → P`)

------------------------------------------------------------------------

## Chain Edit -- Block Selection

  Key               Action
  ----------------- --------------------------
  `V`               Set block start (anchor)
  *(move cursor)*   Extend block selection

Block selection is shown using reverse video.

------------------------------------------------------------------------

## Chain Edit -- Block Operations

  Key   Action
  ----- -----------------------------
  `Y`   Yank (copy block)
  `X`   Cut block
  `P`   Paste (clipboard / section)
  `F`   Flush clipboard

------------------------------------------------------------------------

## Chain Edit -- Section Labels

  Key   Action
  ----- --------------------------------
  `S`   Attach section label at cursor
  `R`   Remove section label at cursor

Notes: - Section labels are metadata only. - `S` opens a prompt. - `R`
removes label at cursor. - Outside Chain focus, `R` keeps its original
meaning.

------------------------------------------------------------------------

## Chain Edit -- Pattern Editing

  Key       Action
  --------- ----------------------------------------
  `Enter`   Open StepSeq for the pattern at cursor

------------------------------------------------------------------------

## Insert (Focus-aware)

  Focus          Key       Action
  -------------- --------- --------------------------
  ARR list       `Enter`   Insert after cursor
  ARR list       `O / o`   Insert before cursor
  Pattern list   `Enter`   Insert / increase repeat
  Pattern list   `O / o`   Insert before cursor

------------------------------------------------------------------------

# Step Sequencer (StepSeq v3.0a)

Supported grids:

-   **32-step** (straight)
-   **24-step** (8T triplet)
-   **48-step** (16T triplet)

Half pattern (`_h`):

-   `PLAY_BARS = 1`
-   Second bar visually disabled but editable

Bar separators are explicitly shown.

------------------------------------------------------------------------

## StepSeq -- Navigation

  Key               Action
  ----------------- ---------------
  `h / j / k / l`   Move cursor
  `[`               Go to 1st bar
  `]`               Go to 2nd bar

Pattern length is fixed at 2 bars.

------------------------------------------------------------------------

## StepSeq -- Editing

  Key          Action
  ------------ ---------------------------------------
  `Enter`      Stamp note (Replace policy)
  `r`          Record Arm cycle (STBY → ARMED → REC)
  `Ctrl + Z`   Undo (take-level)

Replace policy: - Repeated hits overwrite with the latest velocity.

Undo scope: - Last take (manual input or recorded pass).

------------------------------------------------------------------------

## StepSeq -- Loop

  Key   Action
  ----- -----------------------------------
  `O`   Toggle Loop Scope (BAR ↔ PATTERN)

Loop is always active.\
Scope determines playback range only.

Playback cursor follows active bar in PATTERN scope.

------------------------------------------------------------------------

## StepSeq -- Destructive (Editor Only)

  Key    Action
  ------ ---------------
  `F7`   Delete Row
  `F8`   Delete Column
  `F9`   Delete Bar

Destructive operations intentionally mapped to function keys.

------------------------------------------------------------------------

## Design Notes (Mental Model)

-   **ADT** = Pattern (reusable rhythmic unit)
-   **ARR** = Arrangement (ordered structure of patterns)
-   Chain represents a linear time axis
-   Sections are labels only
-   Bar counts and positions are computed, not stored
