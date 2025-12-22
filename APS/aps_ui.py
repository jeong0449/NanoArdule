# ================================================================
# APS_UI - Build/Version Stamp
# ------------------------------------------------
# BUILD_DATE_KST : 2025-12-17
# BUILD_TAG      : aps_ui-20251217
# CHANGE_NOTE    : UI: Norton Commander style dialog_confirm/dialog_alert (no shadow, no title).
#
# Tip: If you are using git, also record the commit hash:
#   git rev-parse --short HEAD
# ================================================================

APS_UI_BUILD_DATE_KST = "2025-12-17"
APS_UI_BUILD_TAG = "aps_ui-20251217"
APS_UI_CHANGE_NOTE = 'UI: Norton Commander style dialog_confirm/dialog_alert (no shadow, no title).'

# aps_ui.py — curses UI helpers for APS v0.27+
import curses
from typing import List, Optional, Tuple

from aps_core import Pattern, ChainEntry, compute_timing, describe_timing, HIT_CHAR
from aps_sections import ChainSelection, SectionManager
from aps_countin import get_countin_presets   # (for Help / Count-in menu guidance)


def draw_grid(pattern: Optional[Pattern], win, current_step, use_color, color_pairs):
    """
    Pattern grid preview.
    """
    win.erase()
    h, w = win.getmaxyx()
    win.box()

    if not pattern:
        try:
            win.addstr(1, 1, "패턴 선택 필요")
        except curses.error:
            pass
        win.refresh()
        return

    title = f" Grid Preview ({describe_timing(pattern)}) "
    try:
        win.addstr(0, 2, title[:w - 4])
    except curses.error:
        pass

    # --- Layout settings ---
    label_w = 4  # 왼쪽 KK/SN 같은 약자 자리
    inner_w = w - 2

    # Right-side instrument description texts (format: "KK: KICK")
    instr_texts = [
        f"{abbr}: {name}"
        for abbr, name in zip(pattern.slot_abbr, pattern.slot_name)
    ]
    if instr_texts:
        max_instr_len = max(len(t) for t in instr_texts)
    else:
        max_instr_len = 0
    instr_w = min(max_instr_len + 1, max(10, inner_w // 3))  # 최소 10, 최대 1/3 정도

    # Max X coordinate available for the grid area
    grid_max_x = w - 1 - instr_w - 1  # 오른쪽 테두리 - 악기컬럼 - 1칸 여유
    if grid_max_x <= label_w + 1:
        # If too narrow, drop the instrument column and draw only the grid
        grid_max_x = w - 2
        instr_w = 0

    # Timing info
    beats, bars, spb, spbar = compute_timing(pattern)

    # Reverse slot order so KK appears at the bottom
    slots = list(range(pattern.slots - 1, -1, -1))

    # --- Grid + right-side instrument descriptions ---
    for row_idx, s in enumerate(slots):
        y = 1 + row_idx
        # Reserve the very last row for the legend
        if y >= h - 2:
            break

        # Slot label (abbreviation)
        label = pattern.slot_abbr[s]
        try:
            win.addstr(y, 1, f"{label:>3} ")
        except curses.error:
            pass

        grid_start_x = 1 + label_w

        # Convert step -> visual_step (insert one blank column between bars)
        for step in range(pattern.length):
            if spbar > 0:
                visual_step = step + (step // spbar)
            else:
                visual_step = step

            x = grid_start_x + visual_step
            if x >= grid_max_x:
                break

            acc = pattern.grid[step][s]

            attr = 0
            ch = HIT_CHAR

            if current_step is not None and current_step == step:
                # Current playing step: use 'play' color; show '|' when no-hit
                ch = HIT_CHAR if acc > 0 else "|"
                if use_color:
                    try:
                        attr |= curses.color_pair(color_pairs["play"])
                    except Exception:
                        pass
            else:
                if acc == 0:
                    # No-hit dot: alternate color per beat
                    ch = "·"
                    if use_color:
                        if spb > 0 and beats > 0:
                            beat_idx = (step // spb) % beats
                            key = "n" if (beat_idx % 2) == 0 else "n2"
                        else:
                            key = "n"
                        try:
                            attr |= curses.color_pair(color_pairs[key])
                        except Exception:
                            pass
                else:
                    # Accented hit
                    if acc == 1:
                        key = "acc1"
                    elif acc == 2:
                        key = "acc2"
                    else:
                        key = "acc3"
                    if use_color:
                        try:
                            attr |= curses.color_pair(color_pairs[key])
                        except Exception:
                            pass

            try:
                win.addch(y, x, ch, attr)
            except curses.error:
                pass

        # Right-side instrument column (KK: KICK)
        if instr_w > 0:
            instr_x = grid_max_x + 1  # 그리드 끝 + 1칸
            text = f"{pattern.slot_abbr[s]}: {pattern.slot_name[s]}"
            try:
                win.addstr(y, instr_x, text[:instr_w].ljust(instr_w))
            except curses.error:
                pass

    # --- Bottom row: no-hit + accent legend ---
    legend_y = h - 2
    try:
        win.hline(legend_y, 1, " ", w - 2)
    except curses.error:
        pass

    x = 1
    try:
        win.addstr(legend_y, x, "Legend: ")
    except curses.error:
        pass
    x += len("Legend: ")

    # Even-beat no-hit (white)
    if use_color:
        try:
            win.addch(legend_y, x, "·", curses.color_pair(color_pairs.get("n", 0)))
        except curses.error:
            pass
    else:
        try:
            win.addch(legend_y, x, "·")
        except curses.error:
            pass
    x += 2
    try:
        win.addstr(legend_y, x, "even  ")
    except curses.error:
        pass
    x += len("even  ")

    # Odd-beat no-hit (cyan)
    if use_color:
        try:
            win.addch(legend_y, x, "·", curses.color_pair(color_pairs.get("n2", 0)))
        except curses.error:
            pass
    else:
        try:
            win.addch(legend_y, x, "·")
        except curses.error:
            pass
    x += 2
    try:
        win.addstr(legend_y, x, "odd   ")
    except curses.error:
        pass
    x += len("odd   ")

    # Accent blocks: soft/med/strong + play
    def draw_accent_block(label: str, key: str):
        nonlocal x
        try:
            win.addch(
                legend_y,
                x,
                HIT_CHAR,
                curses.color_pair(color_pairs[key]) if use_color else 0,
            )
        except curses.error:
            pass
        x += 2
        txt = f"{label}  "
        try:
            win.addstr(legend_y, x, txt)
        except curses.error:
            pass
        x += len(txt)

    draw_accent_block("soft", "acc1")
    draw_accent_block("med", "acc2")
    draw_accent_block("strong", "acc3")
    draw_accent_block("play", "play")

    win.refresh()


def draw_chain_view(
    win,
    chain: List[ChainEntry],
    chain_len: int,
    focus_chain: bool,
    selected_idx: int,
    selection: ChainSelection,
    section_mgr: SectionManager,
    countin_label: str,
):
    """
    Chain view:
    - sel_range: block selection range (always reversed)
    - selected_idx: current insertion cursor (always shown even without focus)
    - Focused window shows ▶ before the title; selected line is reverse+bold
    - Unfocused window has a leading space in title; selected line is yellow+bold
    - countin_label: currently selected Count-in state (e.g., None, SimpleHH...)
    """
    win.erase()
    h, w = win.getmaxyx()
    win.box()

    ci = countin_label or "None"
    if focus_chain:
        title = f" ▶ Pattern Chain (len={chain_len}) — APS v0.27+ [CI:{ci}] "
    else:
        title = f"   Pattern Chain (len={chain_len}) — APS v0.27+ [CI:{ci}] "

    try:
        win.addstr(0, 2, title[:w - 4])
    except curses.error:
        pass

    if not chain:
        try:
            win.addstr(1, 2, "Chain is empty.")
        except curses.error:
            pass
        win.refresh()
        return

    max_rows = h - 2
    start = 0
    if selected_idx >= max_rows:
        start = selected_idx - max_rows + 1

    sel_range = selection.get_range()

    for row in range(start, min(start + max_rows, len(chain))):
        y = 1 + (row - start)
        entry = chain[row]
        label = f"[{entry.section}] " if entry.section else ""
        line = f"{row + 1:02d}: {label}{entry.filename} x{entry.repeats}"

        if sel_range and sel_range[0] <= row <= sel_range[1]:
            # Block selection: always reversed
            try:
                win.addstr(y, 1, line[:w - 2].ljust(w - 2), curses.A_REVERSE)
            except curses.error:
                pass
        elif row == selected_idx:
            # Highlighted cursor: always shown regardless of focus
            if focus_chain:
                # Chain window focused: reverse + bold
                attr = curses.A_REVERSE | curses.A_BOLD
            else:
                # Unfocused: yellow + bold (or just bold if color unavailable)
                attr = curses.A_BOLD
                try:
                    attr |= curses.color_pair(10)  # Pair 10: yellow (initialized in main)
                except curses.error:
                    pass
            try:
                win.addstr(y, 1, line[:w - 2].ljust(w - 2), attr)
            except curses.error:
                pass
        else:
            try:
                win.addstr(y, 1, line[:w - 2].ljust(w - 2))
            except curses.error:
                pass

    win.refresh()


def draw_status(stdscr, midi_port, bpm, mode, msg, repeat_mode):
    max_y, max_x = stdscr.getmaxyx()
    line = f"MIDI:{midi_port or '(none)'} | BPM:{bpm} | MODE:{mode} | REPEAT:{'ON' if repeat_mode else 'OFF'}"
    if msg:
        line += " | " + msg
    try:
        stdscr.attron(curses.A_REVERSE)
        stdscr.addstr(max_y - 1, 0, line[:max_x - 1].ljust(max_x - 1))
        stdscr.attroff(curses.A_REVERSE)
    except curses.error:
        pass


def draw_menu(stdscr):
    """
    Draw the top menu bar.
    F-key mapping (latest for v0.27):

    F1: Help
    F2: Pat/ARR
    F3: Refresh
    F4: SongStructure
    F5: Info (Pattern Info)
    F6: MIDI Port
    F7: Save ARR
    F8: Count-in
    F9: BPM
    q/F10: Quit
    """
    max_y, max_x = stdscr.getmaxyx()

    menu_text = (
        " F1 Help "
        " F2 Pat/ARR "
        " F3 Refresh "
        " F4 SongStruct "
        " F5 Info "
        " F6 MIDI "
        " F7 SaveARR "
        " F8 CountIn "
        " F9 BPM "
        " q/F10 Quit "
    )

    # 상단 한 줄을 역상으로 칠하고, 길면 잘라내고 짧으면 공백 채우기
    stdscr.attron(curses.A_REVERSE)
    stdscr.addnstr(0, 0, menu_text.ljust(max_x), max_x)
    stdscr.attroff(curses.A_REVERSE)


def show_pattern_info_curses(stdscr, p: Pattern):
    """Show pattern info in a centered popup window.

    Notes:
      - Handles terminal resize (KEY_RESIZE) by rebuilding the popup.
      - Exits on any non-resize key.
    """
    lines = [
        f"Name : {p.name}",
        f"Path : {p.path}",
        f"Length: {p.length} steps",
        f"Slots : {p.slots}",
        f"Time  : {p.time_sig}",
        f"Grid  : {p.grid_type} ({'triplet' if p.triplet else 'straight'})",
        "",
        "Slot mapping (abbr -> name / note):",
    ]

    for i in range(p.slots):
        abbr = p.slot_abbr[i] if i < len(p.slot_abbr) else "??"
        name = p.slot_name[i] if i < len(p.slot_name) else "UNKNOWN"
        note = p.slot_note[i] if i < len(p.slot_note) else -1
        lines.append(f"  {i:02d}. {abbr:>2} -> {name} / {note}")

    lines.extend(
        [
            "",
            "Legend:",
            "  · '.'       : rest",
            "  · '-'       : soft (acc1)",
            "  · 'x'       : medium (acc2)",
            "  · 'o'       : strong (acc3)",
            "",
            "Preview colors (if enabled):",
            "  · (white)  : no hit on even beats",
            "  · (cyan)   : no hit on odd beats",
            "  x (green)  : soft accent (acc1)",
            "  x (yellow) : medium accent (acc2)",
            "  x (red)    : strong accent (acc3)",
            "  x (blue)   : current playing step",
            "",
            "Press any key to close (resize is supported).",
        ]
    )

    def draw_popup():
        max_y, max_x = stdscr.getmaxyx()
        # popup size
        h = min(len(lines) + 2, max(6, max_y - 2))
        w = min(max(len(s) for s in lines) + 4, max(20, max_x - 2))
        y = max(0, (max_y - h) // 2)
        x = max(0, (max_x - w) // 2)

        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        win.erase()
        win.box()

        visible = lines[: max(1, h - 2)]
        for i, s in enumerate(visible):
            try:
                win.addstr(1 + i, 2, s[: max(1, w - 4)])
            except curses.error:
                pass

        win.refresh()
        return win

    win = draw_popup()
    while True:
        ch = win.getch()
        if ch == curses.KEY_RESIZE:
            # Recompute terminal dimensions and rebuild popup
            try:
                curses.update_lines_cols()
            except Exception:
                pass
            try:
                curses.resizeterm(*stdscr.getmaxyx())
            except Exception:
                pass
            stdscr.erase()
            stdscr.refresh()
            win = draw_popup()
            continue
        break

    # Clear popup remnants and let caller redraw
    stdscr.touchwin()
    stdscr.refresh()

def prompt_text(stdscr, prompt: str, maxlen: int = 40) -> Optional[str]:
    """
    Simple line input dialog at the bottom of the screen.

    - ESC: cancel immediately, return None (no "^[" printed)
    - Enter: accept current text (may be empty string)
    - Backspace: delete last char
    - Printable ASCII only
    """
    max_y, max_x = stdscr.getmaxyx()

    win_h = 3
    win_w = min(max_x - 2, max(len(prompt) + maxlen + 4, 20))
    y = max_y - win_h
    x = 1

    win = stdscr.derwin(win_h, win_w, y, x)
    win.keypad(True)

    curses.curs_set(1)
    curses.noecho()

    text = ""

    while True:
        win.erase()
        win.box()
        try:
            # Prompt + current input text
            display = f"{prompt} {text}"
            win.addstr(1, 2, display[: win_w - 4])
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()

        # Enter: accept
        if ch in (10, 13):
            curses.curs_set(0)
            return text

        # ESC: cancel immediately (no "^[" on screen)
        if ch == 27:
            curses.curs_set(0)
            return None

        # Backspace
        if ch in (curses.KEY_BACKSPACE, 127, 8):
            if text:
                text = text[:-1]
            continue

        # Printable ASCII
        if 32 <= ch <= 126:
            if len(text) < maxlen:
                text += chr(ch)
            continue

        # Other keys are ignored
        continue


def show_message(stdscr, msg):
    max_y, max_x = stdscr.getmaxyx()
    try:
        stdscr.addstr(max_y - 2, 1, msg[: max_x - 2].ljust(max_x - 2))
    except curses.error:
        pass
    stdscr.refresh()


def choose_midi_port_curses(stdscr) -> Optional[str]:
    import mido

    try:
        ports = mido.get_output_names()
    except Exception:
        return None
    if not ports:
        return None

    max_y, max_x = stdscr.getmaxyx()
    h = min(len(ports) + 4, max_y - 2)
    w = max(max(len(p) for p in ports) + 4, 20)
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    idx = 0

    while True:
        win.clear()
        win.box()
        try:
            win.addstr(0, 2, " Select MIDI Out ")
        except curses.error:
            pass
        for i, p in enumerate(ports[: h - 2]):
            line = f" {p} "
            if i == idx:
                win.attron(curses.A_REVERSE)
                win.addstr(2 + i, 1, line[: w - 2].ljust(w - 2))
                win.attroff(curses.A_REVERSE)
            else:
                win.addstr(2 + i, 1, line[: w - 2].ljust(w - 2))
        win.refresh()

        ch = win.getch()
        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(ports)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(ports)
        elif ch in (10, 13):
            return ports[idx]
        elif ch in (27, ord("q")):
            return None


# ======== Section overview / choose block+section / paste position / choose count-in / help ========

def show_section_overview_curses(
    stdscr, chain: List[ChainEntry], section_mgr: SectionManager, current_idx: int
):
    """
    Popup window that shows all sections registered in SectionManager.
    (section name + row range + length)
    """
    max_y, max_x = stdscr.getmaxyx()
    lines: List[str] = []

    names = section_mgr.list_sections()
    if not names:
        lines.append("No sections defined.")
    else:
        for name in names:
            entries = section_mgr.section_entries(chain, name)
            if not entries:
                continue
            rng = section_mgr.get_section_range(name)
            if rng:
                start, end = rng
                mark = " "
                if start <= current_idx <= end:
                    mark = "*"
                lines.append(
                    f"{mark} {name}: rows {start+1}-{end+1} ({end-start+1} steps)"
                )
            else:
                lines.append(f"  {name}: (range unknown)")

    h = min(len(lines) + 4, max_y - 2)
    w = min(max((len(s) for s in lines), default=20) + 4, max_x - 2)
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.erase()
    win.box()
    try:
        win.addstr(0, 2, " Sections Overview / Song Structure ")
    except curses.error:
        pass

    for i, s in enumerate(lines[: h - 3]):
        try:
            win.addstr(1 + i, 2, s[: w - 4])
        except curses.error:
            pass

    try:
        win.addstr(h - 2, 2, "Press any key...")
    except curses.error:
        pass
    win.refresh()
    win.getch()


def choose_block_or_section_curses(
    stdscr,
    clipboard: List[ChainEntry],
    section_mgr: SectionManager,
    chain: List[ChainEntry],
) -> Optional[Tuple[List[ChainEntry], str]]:
    """
    Called on paste: choose what to paste from the clipboard or defined sections.
    Select which block to paste.
    Returns: (entries_to_paste, label) or None
    """
    items: List[Tuple[str, List[ChainEntry]]] = []

    # 1) Clipboard
    if clipboard:
        label = f"[Clipboard] {len(clipboard)} step(s)"
        entries = [ChainEntry(e.filename, e.repeats) for e in clipboard]
        items.append((label, entries))

    # 2) Sections
    names = section_mgr.list_sections()
    for name in names:
        entries = section_mgr.section_entries(chain, name)
        if not entries:
            continue
        label = f"[Section] {name} ({len(entries)} step(s))"
        copies = [ChainEntry(e.filename, e.repeats) for e in entries]
        items.append((label, copies))

    if not items:
        show_message(stdscr, "Nothing to paste (no clipboard / sections)")
        return None

    max_y, max_x = stdscr.getmaxyx()
    h = min(len(items) + 4, max_y - 2)
    w = min(
        max(len(lbl) for (lbl, _) in items) + 4,
        max_x - 2,
    )
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    idx = 0

    while True:
        win.erase()
        win.box()
        try:
            win.addstr(0, 2, " Paste: choose block ")
        except curses.error:
            pass

        for i, (label, _) in enumerate(items[: h - 3]):
            if i == idx:
                try:
                    win.attron(curses.A_REVERSE)
                    win.addstr(1 + i, 2, label[: w - 4].ljust(w - 4))
                    win.attroff(curses.A_REVERSE)
                except curses.error:
                    pass
            else:
                try:
                    win.addstr(1 + i, 2, label[: w - 4].ljust(w - 4))
                except curses.error:
                    pass

        try:
            win.addstr(h - 2, 2, "Enter: select  Esc/q: cancel")
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()

        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (10, 13):
            label, entries = items[idx]
            return entries, label
        elif ch in (27, ord("q")):
            return None


def choose_paste_position_curses(stdscr) -> Optional[str]:
    """
    After paste, choose whether to paste the selected block before or after the current line.
    Returns: "before" / "after" / None
    """
    max_y, max_x = stdscr.getmaxyx()
    options = ["After current line", "Before current line"]
    idx = 0

    h = 6
    w = max(len(options[0]), len(options[1])) + 6
    w = min(w, max_x - 2)
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    while True:
        win.erase()
        win.box()
        try:
            win.addstr(0, 2, " Paste position ")
        except curses.error:
            pass

        for i, opt in enumerate(options):
            text = opt[: w - 4].ljust(w - 4)
            if i == idx:
                try:
                    win.attron(curses.A_REVERSE)
                    win.addstr(1 + i, 2, text)
                    win.attroff(curses.A_REVERSE)
                except curses.error:
                    pass
            else:
                try:
                    win.addstr(1 + i, 2, text)
                except curses.error:
                    pass

        try:
            win.addstr(h - 2, 2, "↑/↓+Enter, Esc=cancel")
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()

        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(options)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(options)
        elif ch in (10, 13):
            return "after" if idx == 0 else "before"
        elif ch in (27, ord("q")):
            return None


def choose_countin_curses(stdscr, current_idx: int) -> Optional[int]:
    """
    F3: Count-in preset selection popup.
    - First row is (None)
    - The rest are builtin pattern names defined in aps_countin.py
    Returns: -1 = None, 0..N-1 = selected preset index, None = canceled
    """
    presets = get_countin_presets()
    names = [p.name for p in presets]

    items = ["(None)"] + names
    # current_idx는 0..N-1 또는 -1
    idx = 0 if current_idx < 0 else current_idx + 1

    max_y, max_x = stdscr.getmaxyx()
    h = min(len(items) + 5, max_y - 2)
    w = min(max(len(s) for s in items) + 4, max_x - 2)
    if w < 30:
        w = 30
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.keypad(True)

    while True:
        win.erase()
        win.box()
        try:
            win.addstr(0, 2, " Count-in Preset ")
        except curses.error:
            pass

        limit = h - 3  # 마지막 줄은 안내 메시지
        for i, s in enumerate(items[: limit]):
            text = f" {s} "
            if i == idx:
                try:
                    win.attron(curses.A_REVERSE)
                    win.addstr(1 + i, 2, text[: w - 4].ljust(w - 4))
                    win.attroff(curses.A_REVERSE)
                except curses.error:
                    pass
            else:
                try:
                    win.addstr(1 + i, 2, text[: w - 4].ljust(w - 4))
                except curses.error:
                    pass

        # Bottom line: show where these builtin patterns are defined
        info = "Builtin patterns are in aps_countin.py"
        try:
            win.addstr(h - 2, 2, info[: w - 4])
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()

        if ch in (curses.KEY_UP, ord("k")):
            idx = (idx - 1) % len(items)
        elif ch in (curses.KEY_DOWN, ord("j")):
            idx = (idx + 1) % len(items)
        elif ch in (10, 13):
            # Confirm selection
            if idx == 0:
                return -1   # None
            else:
                return idx - 1
        elif ch in (27, ord("q")):
            # Cancel
            return None


def show_help_curses(stdscr):
    """
    Help popup showing a quick key summary (F1).
    """
    lines = [
        "APS Chain Editor Keys",
        "",
        "[Focus]",
        "  H               : open full keymap (APS_Keymap*.md)",
        "  Tab              : switch focus (Patterns/ARR <-> Chain)",
        "",
        "[Left list (Patterns / ARR)]",
        "  F4               : toggle left list (Patterns <-> ARR) & refresh from disk",
        "",
        "  (Patterns mode)",
        "    Arrow / hjkl   : move selection",
        "    Enter          : add pattern after cursor (merges xN when same)",
        "    O / o          : add pattern before cursor (merges xN when same)",
        "    c              : toggle _P### <-> _B### of selected pattern file",
        "",
        "  (ARR mode)",
        "    Arrow / hjkl   : move selection",
        "    Enter          : insert selected ARR after chain cursor",
        "    O / o          : insert selected ARR before chain cursor",
        "",
        "[Chain basic]",
        "  ↑/↓/PgUp/PgDn/Home/End : move in chain",
        "  - / +                  : decrease/increase repeats (xN)",
        "  Delete / Backspace     : delete (line or repeats, backspace=prev line)",
        "",
        "[Block selection]",
        "  V / v          : start block selection at cursor",
        "  Shift+↑/↓      : extend selection (or use KEY_SR/KEY_SF)",
        "  Delete         : delete selected block",
        "",
        "[Sections]",
        "  s (in chain)   : name selected block as a section",
        "  F2             : show sections overview / song structure",
        "",
        "[Clipboard]",
        "  x / X          : cut selected block",
        "  y / Y          : copy selected block",
        "  p / P          : paste (choose clipboard or section, then position)",
        "",
        "[Count-in]",
        "  F3             : choose count-in preset (or NONE)",
        "  (when playing chain, 1 bar of HH count-in is sent before main chain)",
        "",
        "[ARR files / ADP note]",
        "  F7             : save chain as ARR (ADP steps are saved as .ADT, with warning)",
        "  F8             : load ARR (choose file, restores chain & BPM & #COUNTIN)",
        "  On playback    : chain will NOT start if any referenced pattern file is missing",
        "",
        "[Playback / Misc]",
        "  Space          : play pattern (left) or chain (right)",
        "  r              : toggle repeat (non-Chain focus)",
        "  R (Chain focus) : remove section at cursor",
        "  F5             : pattern info (current preview pattern)",
        "  F6             : choose MIDI out",
        "  F9             : set BPM",
        "  Ctrl+Z         : undo",
        "  q / F10        : quit",
        "",
        "Press any key...",
    ]

    max_y, max_x = stdscr.getmaxyx()
    h = min(len(lines) + 2, max_y - 2)
    w = min(max(len(s) for s in lines) + 4, max_x - 2)
    y = (max_y - h) // 2
    x = (max_x - w) // 2

    win = curses.newwin(h, w, y, x)
    win.box()
    for i, s in enumerate(lines[: h - 2]):
        try:
            win.addstr(1 + i, 2, s[: w - 4])
        except curses.error:
            pass
    win.refresh()
    win.getch()
# ======== Norton-Commander style dialogs (added) ========

def _wrap_lines(text: str, width: int) -> List[str]:
    """Wrap text into lines not exceeding width (simple word wrap)."""
    if width <= 1:
        return [text[:1]]
    words = text.split()
    if not words:
        return [""]
    lines: List[str] = []
    cur = words[0]
    for w in words[1:]:
        if len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _nc_dialog(
    stdscr,
    message: str,
    buttons: Tuple[str, ...] = ("OK",),
    default: int = 0,
    min_w: int = 34,
    pad_w: int = 6,
    pad_h: int = 6,
) -> int:
    """Norton Commander-style modal dialog (no title, no shadow).

    Returns selected button index.
    Keys:
      - Left/Right/Tab: move selection
      - Enter: confirm
      - Esc: cancel => returns last button index if 2+ buttons else 0
      - Resize: redraw
    """
    if not buttons:
        buttons = ("OK",)
    sel = max(0, min(default, len(buttons) - 1))

    while True:
        max_y, max_x = stdscr.getmaxyx()

        inner_max_w = max(10, max_x - 4)
        wrap_w = max(10, inner_max_w - pad_w)

        lines: List[str] = []
        for para in message.split("\n"):
            if para.strip():
                lines.extend(_wrap_lines(para, wrap_w))
            else:
                lines.append("")

        btn_tokens = [f"[{b}]" for b in buttons]
        btn_row = "  ".join(btn_tokens)

        content_w = max(max((len(s) for s in lines), default=0), len(btn_row))
        w = min(max(min_w, content_w + pad_w), max_x - 2) if max_x >= 10 else max_x
        w = max(10, w)

        content_h = len(lines)
        h = min(max(7, content_h + pad_h), max_y - 2) if max_y >= 10 else max_y
        h = max(7, h)

        y = max(0, (max_y - h) // 2)
        x = max(0, (max_x - w) // 2)

        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        win.erase()
        win.box()

        msg_x = 3
        msg_y = 2
        max_msg_lines = max(1, h - 5)
        for i, s in enumerate(lines[:max_msg_lines]):
            try:
                win.addnstr(msg_y + i, msg_x, s, max(1, w - 6))
            except curses.error:
                pass

        btn_y = h - 3
        btn_row_len = len(btn_row)
        btn_x = max(2, (w - btn_row_len) // 2)

        cur_x = btn_x
        for i, token in enumerate(btn_tokens):
            attr = curses.A_REVERSE if i == sel else 0
            try:
                win.addstr(btn_y, cur_x, token, attr)
            except curses.error:
                pass
            cur_x += len(token)
            if i != len(btn_tokens) - 1:
                try:
                    win.addstr(btn_y, cur_x, "  ")
                except curses.error:
                    pass
                cur_x += 2

        win.refresh()
        ch = win.getch()

        if ch == curses.KEY_RESIZE:
            try:
                curses.update_lines_cols()
            except Exception:
                pass
            try:
                curses.resizeterm(*stdscr.getmaxyx())
            except Exception:
                pass
            continue

        if ch in (10, 13):
            try:
                win.erase()
                win.refresh()
            except Exception:
                pass
            del win
            stdscr.touchwin()
            stdscr.refresh()
            return sel

        if ch == 27:
            try:
                win.erase()
                win.refresh()
            except Exception:
                pass
            del win
            stdscr.touchwin()
            stdscr.refresh()
            return (len(buttons) - 1) if len(buttons) >= 2 else 0

        if ch in (curses.KEY_LEFT, ord("h")):
            sel = (sel - 1) % len(buttons)
        elif ch in (curses.KEY_RIGHT, ord("l"), 9):
            sel = (sel + 1) % len(buttons)
        else:
            pass


def dialog_input(
    stdscr,
    prompt: str,
    default_text: str = "",
    maxlen: int = 64,
    suffix: str = "",
    visible_len: int | None = None,
) -> str | None:
    """
    Norton-Commander style centered input dialog.

    - Editable input field is shown in reverse video.
    - Optional `suffix` (e.g., '.ARR') is shown to the right and is NOT editable.
    - Returns the entered base string (without suffix), or None if canceled (ESC).
    """
    import curses

    h = 7

    # How wide the editable field should look (independent from maxlen restriction).
    if visible_len is None:
        visible_len = min(maxlen, 24)
    else:
        visible_len = max(1, min(visible_len, maxlen))

    # Reserve space for " "+suffix on the same line.
    extra_for_suffix = (1 + len(suffix)) if suffix else 0

    # Width heuristic (keep conservative)
    content_w = max(len(prompt), visible_len + extra_for_suffix)
    w = max(44, min(70, content_w + 12))

    max_y, max_x = stdscr.getmaxyx()
    y = max(0, (max_y - h) // 2)
    x = max(0, (max_x - w) // 2)

    win = curses.newwin(h, w, y, x)
    win.keypad(True)
    win.box()

    # Prompt
    try:
        win.addstr(1, 2, prompt[: w - 4], curses.A_NORMAL)
    except curses.error:
        pass

    field_y = 3
    field_x = 2
    field_total_w = w - 4  # inside border width

    # IMPORTANT: editable_w must NOT eat suffix area.
    reserve = extra_for_suffix if suffix else 0
    editable_w = max(1, min(visible_len, field_total_w - reserve))

    # Footer hint
    hint = "Enter=OK  Esc=Cancel"
    if len(hint) < w - 4:
        try:
            win.addstr(5, w - 2 - len(hint), hint, curses.A_NORMAL)
        except curses.error:
            pass

    text = (default_text or "")[:maxlen]
    cursor = min(len(text), editable_w)

    try:
        curses.curs_set(1)
    except Exception:
        pass

    def _draw_line():
        """Redraw the whole input line safely: NORMAL clear -> REVERSE editable -> NORMAL suffix."""
        # 1) clear whole line in NORMAL (so reverse doesn't "infect" the rest)
        try:
            win.addstr(field_y, field_x, " " * field_total_w, curses.A_NORMAL)
        except curses.error:
            pass

        # 2) draw editable field area in REVERSE
        shown = text[:editable_w].ljust(editable_w)
        try:
            win.addstr(field_y, field_x, shown, curses.A_REVERSE)
        except curses.error:
            pass

        # 3) draw suffix in NORMAL (bold helps visibility)
        if suffix:
            sx = field_x + editable_w + 1  # one space gap
            avail = field_total_w - (editable_w + 1)
            if avail > 0:
                try:
                    win.addstr(field_y, sx, suffix[:avail], curses.A_BOLD)
                except curses.error:
                    pass

    while True:
        _draw_line()

        # Cursor stays within editable field only
        cx = field_x + min(cursor, max(0, editable_w - 1))
        try:
            win.move(field_y, cx)
        except curses.error:
            pass

        win.refresh()
        ch = win.getch()

        # ESC: cancel
        if ch == 27:
            try:
                curses.curs_set(0)
            except Exception:
                pass
            return None

        # Enter: accept
        if ch in (10, 13, curses.KEY_ENTER):
            try:
                curses.curs_set(0)
            except Exception:
                pass
            return text.strip()

        # Backspace variants
        if ch in (curses.KEY_BACKSPACE, 8, 127):
            if cursor > 0:
                text = text[: cursor - 1] + text[cursor:]
                cursor -= 1
            continue

        # Delete
        if ch == curses.KEY_DC:
            if cursor < len(text):
                text = text[:cursor] + text[cursor + 1 :]
            continue

        # Left/Right/Home/End
        if ch == curses.KEY_LEFT:
            cursor = max(0, cursor - 1)
            continue
        if ch == curses.KEY_RIGHT:
            cursor = min(min(len(text), editable_w), cursor + 1)
            continue
        if ch == curses.KEY_HOME:
            cursor = 0
            continue
        if ch == curses.KEY_END:
            cursor = min(len(text), editable_w)
            continue

        # Printable ASCII only
        if 32 <= ch <= 126:
            if len(text) < maxlen and cursor < editable_w:
                text = text[:cursor] + chr(ch) + text[cursor:]
                cursor += 1
            continue


def dialog_alert(stdscr, message: str, button: str = "OK") -> None:
    """Show a NC-style alert dialog. Returns after confirmation."""
    _nc_dialog(stdscr, message, buttons=(button,), default=0)
    return


def dialog_confirm(
    stdscr,
    message: str,
    yes_label: str = "YES",
    no_label: str = "NO",
    default_yes: bool = False,
) -> bool:
    """Show a NC-style confirm dialog. Returns True for YES, False for NO/ESC."""
    default = 0 if default_yes else 1
    idx = _nc_dialog(stdscr, message, buttons=(yes_label, no_label), default=default)
    return idx == 0
