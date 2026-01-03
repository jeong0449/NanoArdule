# ================================================================
# APS_MAIN - Build/Version Stamp
# ------------------------------------------------
# BUILD_DATE_KST : 2025-12-17
# BUILD_TAG      : aps_main-20251217
# CHANGE_NOTE    : Unified main: NC dialogs, warnings, ARR #COUNTIN, shared MIDI out_port, color re-init.
#
# Tip: If you are using git, also record the commit hash:
#   git rev-parse --short HEAD
# ================================================================

APS_MAIN_BUILD_DATE_KST = "2025-12-17"
APS_MAIN_BUILD_TAG = "aps_main-20251217"
APS_MAIN_CHANGE_NOTE = 'Unified main: NC dialogs, warnings, ARR #COUNTIN, shared MIDI out_port, color re-init.'


def write_adt_file_v22a(path: str, pat):
    """
    Write ADT v2.2a in APS canonical KEY=VALUE header + SLOTn=ABBR@NOTE,NAME format
    and grid with symbols ".-xo" (0..3).
    """
    lines = []
    # Header
    lines.append("; ADT v2.2a")
    # Preserve NAME if available
    name = getattr(pat, "name", None) or os.path.splitext(os.path.basename(path))[0]
    lines.append(f"NAME={name}")
    if getattr(pat, "time_sig", None):
        lines.append(f"TIME_SIG={pat.time_sig}")
    lines.append(f"GRID={getattr(pat, 'grid_type', '16')}")
    lines.append(f"LENGTH={getattr(pat, 'length', 32)}")
    lines.append(f"SLOTS={getattr(pat, 'slots', 12)}")
    if getattr(pat, "kit", None):
        lines.append(f"KIT={pat.kit}")
    if getattr(pat, "orientation", None):
        lines.append(f"ORIENTATION={pat.orientation}")

    # Slots
    slots = int(getattr(pat, "slots", 0) or 0)
    for i in range(slots):
        abbr = pat.slot_abbr[i] if hasattr(pat, "slot_abbr") and i < len(pat.slot_abbr) else f"S{i}"
        note = pat.slot_note[i] if hasattr(pat, "slot_note") and i < len(pat.slot_note) else 0
        nm = pat.slot_name[i] if hasattr(pat, "slot_name") and i < len(pat.slot_name) else ""
        lines.append(f"SLOT{i}={abbr}@{note},{nm}")

    lines.append("")  # blank line before grid

    # Grid (steps x slots)
    sym = ".-xo"
    for step in getattr(pat, "grid", []):
        row = "".join(sym[max(0, min(3, int(v)))] for v in step[:slots])
        lines.append(row)

    text = "\n".join(lines) + "\n"
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def validate_grid_levels_v22a(pat):
    """Guard: ensure pat.grid uses only 0..3."""
    for si, row in enumerate(getattr(pat, "grid", [])):
        for li, v in enumerate(row):
            try:
                iv = int(v)
            except Exception:
                raise ValueError(f"grid[{si}][{li}] is not int: {v!r}")
            if iv < 0 or iv > 3:
                raise ValueError(f"grid[{si}][{li}] out of range 0..3: {iv}")
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aps_main.py — APS v0.27 main curses loop + Ctrl+Z Undo + block edit + Count-in.
"""

import os
import copy
import curses
import time
from typing import Optional, List

from aps_core import (
    Pattern,
    ChainEntry,
    load_adt,
    load_adp,
    scan_patterns,
    compute_timing,  # (not used directly here, kept for reference)
)
from aps_sections import ChainSelection, SectionManager
from aps_arr import save_arr, parse_arr
from aps_ui import (
    draw_grid,
    draw_chain_view,
    draw_status,
    draw_menu,
    show_pattern_info_curses,
    prompt_text,
    show_message,
    choose_midi_port_curses,
    show_section_overview_curses,
    choose_block_or_section_curses,
    choose_paste_position_curses,
    show_help_curses,
    choose_countin_curses,
    dialog_confirm,
    dialog_alert,
    dialog_input,

)
from aps_chainedit import handle_chain_keys
from aps_countin import get_countin_presets  # Built-in count-in patterns (for name/meta)

try:
    import mido
except ImportError:
    mido = None

import aps_stepseq

# Used by show_warning_popup wrapper to call NC-style dialogs without threading stdscr everywhere.
_GLOBAL_STDSCR_FOR_DIALOGS = None

def toggle_p_b(fname: str) -> Optional[str]:
    """
    Toggle the filename suffix between _P### and _B###.
    Example: SWG_P001.ADT -> SWG_B001.ADT
    """
    base, ext = os.path.splitext(fname)
    import re

    m = re.search(r"_([pPbB])(\d{3})$", base)
    if not m:
        return None
    kind = m.group(1).upper()
    num = m.group(2)
    new_kind = "B" if kind == "P" else "P"
    new_base = base[: m.start(1)] + new_kind + num
    return new_base + ext


def find_gs():
    """
    Auto-select a MIDI output port:

    1) Prefer a port whose name does not include 'microsoft'
    2) If all ports are Microsoft, use the first port
    3) If there is no port, return None
    """
    if mido is None:
        return None

    try:
        names = mido.get_output_names()
    except Exception:
        return None

    if not names:
        return None

    # Prefer ports whose name does not include 'microsoft' (case-insensitive).
    non_ms = [n for n in names if "microsoft" not in n.lower()]
    if non_ms:
        return non_ms[0]

    # If all are Microsoft ports, use the first port
    return names[0]


def main_curses(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    global _GLOBAL_STDSCR_FOR_DIALOGS
    _GLOBAL_STDSCR_FOR_DIALOGS = stdscr


    use_color = False    # Whether to use color
    color_pairs = {}
    highlight_unfocused_pair = 0  # Color pair number for unfocused highlight

    def init_main_colors():
        nonlocal use_color, color_pairs, highlight_unfocused_pair
        use_color = False
        color_pairs = {}
        highlight_unfocused_pair = 0
        if curses.has_colors():
            use_color = True
            curses.start_color()
            try:
                curses.use_default_colors()
            except Exception:
                pass
            # main UI pairs (1–99)
            color_pairs = {"n": 1, "n2": 2, "acc1": 3, "acc2": 4, "acc3": 5, "play": 6}
            curses.init_pair(color_pairs["n"], curses.COLOR_WHITE, -1)
            curses.init_pair(color_pairs["n2"], curses.COLOR_CYAN, -1)
            curses.init_pair(color_pairs["acc1"], curses.COLOR_GREEN, -1)
            curses.init_pair(color_pairs["acc2"], curses.COLOR_YELLOW, -1)
            curses.init_pair(color_pairs["acc3"], curses.COLOR_RED, -1)
            curses.init_pair(color_pairs["play"], curses.COLOR_BLUE, -1)
            highlight_unfocused_pair = 10
            curses.init_pair(highlight_unfocused_pair, curses.COLOR_CYAN, -1)

    init_main_colors()


    # Pattern root directory:
    #   - If ./patterns exists, prefer that folder
    #   - If missing, use the current directory (".")
    if os.path.isdir("patterns"):
        root = "patterns"
    else:
        root = "."

    # Pattern / ARR list
    pattern_files: List[str] = scan_patterns(root)
    arr_files: List[str] = sorted(
        f for f in os.listdir(root) if f.lower().endswith(".arr")
    )

    # Left list mode: "patterns" / "arr"
    list_mode: str = "patterns"

    selected_idx = 0
    loaded_pattern: Optional[Pattern] = None
    chain: List[ChainEntry] = []
    chain_selected_idx = 0  # Chain cursor (insertion position)
    focus = "patterns"  # "patterns" or "chain"
    bpm = 120
    repeat_mode = False
    msg = ""
    mode = "VIEW"
    selection = ChainSelection()
    section_mgr = SectionManager()

    def _sync_chain_section_labels_from_mgr():
        """Synchronize per-entry section labels from SectionManager metadata.

        The main chain view renders section names using ChainEntry.section.
        Some operations (e.g., ARR import) update section_mgr metadata
        (split/import/shift) without updating ChainEntry.section fields.
        Call this after any metadata-only section changes.
        """
        # Clear existing labels
        for e in chain:
            e.section = None

        secs = getattr(section_mgr, "sections", None) or {}
        if not chain or not secs:
            return

        for name, rng in secs.items():
            try:
                s, t = rng
            except Exception:
                continue
            try:
                s = int(s)
                t = int(t)
            except Exception:
                continue
            s = max(0, s)
            t = min(len(chain) - 1, t)
            if s > t:
                continue
            for i in range(s, t + 1):
                chain[i].section = name


    # --- Undo stack: (chain, chain_selected_idx, selection, section_mgr, bpm) ---
    undo_stack: List[
        tuple[List[ChainEntry], int, ChainSelection, SectionManager, int]
    ] = []

    # --- Clipboard (cut/copied block) ---
    clipboard: List[ChainEntry] = []

    # --- Count-in state ---
    countin_idx: int = -1  # -1 = none, 0..N-1 = index into get_countin_presets()
    countin_presets: List[Pattern] = get_countin_presets()

    # --- Hybrid / Composite state (A/B sources, composite preview, HYB_P9xx.APT auto numbering) ---
    bar_sources: List[int] = []          # Pattern indices selected as A/B sources (max 2)
    composite_mode: bool = False         # True if in composite preview mode
    composite_swap: bool = False         # False: A1+B2, True: A2+B1
    composite_pattern: Optional[Pattern] = None  # Current composite pattern
    hyb_next_index: int = 901            # Auto-increment index for HYB_P9xx.APT

    # --- "First visible index" of the left list (for page scrolling) ---
    top_index = 0

    def get_countin_label() -> str:
        if countin_idx < 0:
            return "None"
        if 0 <= countin_idx < len(countin_presets):
            return countin_presets[countin_idx].name
        return "?"

    def push_undo():
        # Save current state onto the stack with a deep copy
        snapshot = (
            copy.deepcopy(chain),
            chain_selected_idx,
            copy.deepcopy(selection),
            copy.deepcopy(section_mgr),
            bpm,
        )
        undo_stack.append(snapshot)
        # Drop very old entries (keep only the most recent 100 steps)
        if len(undo_stack) > 100:
            undo_stack.pop(0)

    def load_preview():
        """현재 pattern_files / selected_idx 기반으로 프리뷰 로드 (list_mode=patterns일 때만 의미 있음)."""
        nonlocal loaded_pattern, msg
        if list_mode != "patterns":
            # No preview in ARR mode
            loaded_pattern = None
            return
        if not pattern_files:
            loaded_pattern = None
            return
        if selected_idx < 0 or selected_idx >= len(pattern_files):
            loaded_pattern = None
            return
        # In composite preview mode, use composite_pattern as-is
        if composite_mode and composite_pattern is not None:
            loaded_pattern = composite_pattern
            return

        fname = pattern_files[selected_idx]
        path = os.path.join(root, fname)
        lower = fname.lower()
        try:
            if lower.endswith(".adt"):
                loaded_pattern = load_adt(path)
            elif lower.endswith(".apt"):
                loaded_pattern = load_apt(path)
            else:
                loaded_pattern = load_adp(path)
        except Exception as e:
            loaded_pattern = None
            msg = str(e)

    def reset_composite():
        """합성 상태를 완전히 초기화."""
        nonlocal composite_mode, composite_swap, composite_pattern, bar_sources
        composite_mode = False
        composite_swap = False
        composite_pattern = None
        bar_sources = []

    def load_pattern_by_idx(idx: int) -> Optional[Pattern]:
        """패턴 인덱스로부터 Pattern 로드 (.ADT / .APT / .ADP). 실패 시 None."""
        if idx < 0 or idx >= len(pattern_files):
            return None
        fname = pattern_files[idx]
        path = os.path.join(root, fname)
        lower = fname.lower()
        try:
            if lower.endswith(".adt"):
                return load_adt(path)
            elif lower.endswith(".apt"):
                return load_apt(path)
            else:
                return load_adp(path)
        except Exception:
            return None
###
    def rebuild_composite():
        """bar_sources[0/1] + composite_swap 상태를 바탕으로 composite_pattern 재구성."""
        nonlocal loaded_pattern, composite_pattern, composite_mode, msg
        if len(bar_sources) != 2:
            composite_mode = False
            composite_pattern = None
            return
        a_idx, b_idx = bar_sources[0], bar_sources[1]
        pa = load_pattern_by_idx(a_idx)
        pb = load_pattern_by_idx(b_idx)
        if pa is None or pb is None:
            msg = "A/B pattern load failed"
            composite_mode = False
            composite_pattern = None
            return
        if pa.length != pb.length or pa.slots != pb.slots:
            msg = "A/B length/slots mismatch"
            composite_mode = False
            composite_pattern = None
            return

        length = pa.length
        slots = pa.slots
        grid = [[0] * slots for _ in range(length)]
        half = length // 2 if length >= 2 else length

        if not composite_swap:
            # A1 + B2
            for s in range(half):
                grid[s] = pa.grid[s][:]
            for s in range(half, length):
                grid[s] = pb.grid[s][:]
            mode_name = "A1 + B2"
        else:
            # B1 + A2
            for s in range(half):
                grid[s] = pb.grid[s][:]
            for s in range(half, length):
                grid[s] = pa.grid[s][:]
            mode_name = "B1 + A2"

        p = Pattern(
            name=f"HYB({mode_name})",
            path="",
            length=length,
            slots=slots,
            grid=grid,
            grid_type=pa.grid_type,
            slot_abbr=pa.slot_abbr,
            slot_note=pa.slot_note,
            slot_name=pa.slot_name,
            time_sig=pa.time_sig,
            triplet=pa.triplet,
        )
        composite_pattern = p
        loaded_pattern = p
        composite_mode = True
        msg = f"Composite: {mode_name}"

###
    def save_composite_pattern():
        """현재 composite_pattern을 HYB_P9xx.APT(JSON)으로 저장."""
        nonlocal msg, hyb_next_index, composite_pattern, pattern_files, selected_idx

        if not composite_mode or composite_pattern is None:
            msg = "합성 패턴이 없습니다."
            return
# From here
        default_base = f"HYB_P{hyb_next_index:03d}"

        base = dialog_input(
            stdscr,
            "Save hybrid pattern:",
            default_text=default_base,
            maxlen=64,
            suffix=".APT",
        )

        if base is None:
            msg = "Save canceled."
            return

        base = base.strip()
        if not base:
            base = default_base

        t = base + ".APT"
        path = os.path.join(root, t)


# Up to here
        try:
            p = composite_pattern
            data = {
                "name": p.name,
                "length": p.length,
                "slots": p.slots,
                "grid_type": p.grid_type,
                "time_sig": p.time_sig,
                "triplet": p.triplet,
                "slot_abbr": list(p.slot_abbr),
                "slot_note": list(p.slot_note),
                "slot_name": list(p.slot_name),
                "grid": p.grid,
            }
            with open(path, "w", encoding="utf-8") as f:
                import json as _json  # Local import (same JSON schema as aps_core)
                _json.dump(data, f, ensure_ascii=False, indent=2)

            msg = f"Saved hybrid pattern: {t}"
            hyb_next_index += 1

            # After saving, rescan pattern list (so new HYB_P9xx.APT appears)
            pattern_files = scan_patterns(root)
            try:
                new_idx = pattern_files.index(t)
                selected_idx = new_idx
            except ValueError:
                pass

        except Exception as e:
            msg = f"Hybrid save failed: {e}"

    if pattern_files:
        load_preview()

    def load_countin_from_arr(path: str):
        """ARR 파일에서 # Restore countin_idx by reading the COUNTIN header."""
        nonlocal countin_idx
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.startswith("#COUNTIN"):
                        parts = line.strip().split(None, 1)
                        mode_str = parts[1] if len(parts) > 1 else "NONE"
                        if mode_str.upper() == "NONE":
                            countin_idx = -1
                        else:
                            name = mode_str
                            # Match preset name
                            idx = -1
                            for i, p in enumerate(countin_presets):
                                if p.name == name:
                                    idx = i
                                    break
                            countin_idx = idx
                        break
        except Exception:
            # If missing or failed to read, just ignore
            pass

    def choose_arr_file_curses(stdscr, arrs: List[str]) -> Optional[str]:
        """
        Small popup to choose one ARR file from the list.
        (Not used by function keys currently, kept for reference.)
        """
        if not arrs:
            return None

        max_y, max_x = stdscr.getmaxyx()
        arrs_sorted = sorted(arrs)
        h = min(len(arrs_sorted) + 4, max_y - 2)
        w = min(max(len(a) for a in arrs_sorted) + 4, max_x - 2)
        y = (max_y - h) // 2
        x = (max_x - w) // 2

        win = curses.newwin(h, w, y, x)
        win.keypad(True)
        idx = 0

        while True:
            win.erase()
            win.box()
            try:
                win.addstr(0, 2, " Select ARR file ")
            except curses.error:
                pass

            max_list = h - 3
            for i, fname in enumerate(arrs_sorted[:max_list]):
                text = fname[: w - 4].ljust(w - 4)
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
                win.addstr(h - 2, 2, "↑/↓:move  Enter:load  Esc/q:cancel")
            except curses.error:
                pass

            win.refresh()
            ch = win.getch()
            if ch in (curses.KEY_UP, ord("k")):
                idx = (idx - 1) % len(arrs_sorted)
            elif ch in (curses.KEY_DOWN, ord("j")):
                idx = (idx + 1) % len(arrs_sorted)
            elif ch in (10, 13):
                return arrs_sorted[idx]
            elif ch in (27, ord("q")):
                return None



    def show_warning_popup(lines_to_show: List[str], title: str = "Warning"):
        """
        Show a modal warning popup in reverse video and wait for a key press.
        This is used for non-fatal runtime warnings (e.g., missing patterns, MIDI open failure).
        """
        max_y, max_x = stdscr.getmaxyx()
        content = [ln.rstrip("\n") for ln in (lines_to_show or [])]
        if not content:
            content = ["(no details)"]

        w = min(max_x - 4, max(30, min(max(len(ln) for ln in content) + 6, max_x - 4)))
        h = min(max_y - 4, max(7, min(len(content) + 4, max_y - 4)))
        y0 = (max_y - h) // 2
        x0 = (max_x - w) // 2

        try:
            win = curses.newwin(h, w, y0, x0)
            win.keypad(True)
            win.bkgd(" ", curses.A_REVERSE)
            win.erase()
            win.border()

            if title:
                t = f" {title} "
                if len(t) < w - 2:
                    win.addnstr(0, max(1, (w - len(t)) // 2), t, w - 2, curses.A_REVERSE)

            cap = h - 4
            for i, ln in enumerate(content[:cap]):
                win.addnstr(2 + i, 2, ln.ljust(w - 4), w - 4, curses.A_REVERSE)

            hint = "Press any key to dismiss"
            if len(hint) < w - 4:
                win.addnstr(h - 2, w - len(hint) - 2, hint, len(hint), curses.A_REVERSE)

            win.refresh()
            try:
                curses.flushinp()  # drop any queued key repeats (e.g., held SPACE)
            except Exception:
                pass
            while True:
                k = win.getch()
                # Ignore SPACE so a held trigger key does not instantly dismiss the popup
                if k in (ord(' '), curses.KEY_RESIZE):
                    continue
                if k != -1:
                    break
        except curses.error:
            try:
                show_message(stdscr, content[0], 2.0)
            except Exception:
                pass


    def try_open_midi_output(port_name: Optional[str]) -> Optional[str]:
        """Return None on success, otherwise return an error string."""
        if mido is None:
            return "mido backend is not available."
        if not port_name:
            return "No MIDI output port selected."
        try:
            outp = mido.open_output(port_name)
            try:
                outp.close()
            except Exception:
                pass
            return None
        except Exception as e:
            return str(e)


    def open_stepseq_for_selected_pattern():
        """
        Take the .ADT pattern selected in the current pattern list (2 bars, 32 steps),
        open it in the step sequencer for editing, and apply the result back to pat.grid in memory.
        Press P to play the current StepGrid as MIDI.
        """
        nonlocal loaded_pattern, msg, selected_idx, pattern_files, bpm, midi_port

        # 1) This function only works when the pattern list has focus
        if list_mode != "patterns":
            msg = "StepSeq는 패턴 리스트에서만 사용 가능합니다."
            return
        if not pattern_files or not (0 <= selected_idx < len(pattern_files)):
            msg = "선택된 패턴이 없습니다."
            return

        fname = pattern_files[selected_idx]
        lower = fname.lower()
        if not lower.endswith(".adt"):
            msg = "StepSeq는 .ADT 패턴에서만 사용 가능합니다."
            return

        # 2) Load ADT
        path = os.path.join(root, fname)
        try:
            pat = load_adt(path)
        except Exception as e:
            msg = f"ADT load error: {e}"
            return

        # 3) Only supports 2-bar (32-step) patterns
        if pat.length != 32:
            msg = f"StepSeq: length=32(2bar) 패턴만 지원 (현재 {pat.length})"
            return

        # 4) Drum lanes for StepSeq (METHOD B: use the pattern's SLOT definitions)
        #    - This avoids hard-coded 8-lane mapping and always reflects the ADT's slot list.
        #    - Preserve slot order as defined in the ADT (you can reverse here if you want KICK at bottom).
        drum_lanes = []
        note_to_slot = {}
        for i, note in enumerate(getattr(pat, "slot_note", [])):
            try:
                n = int(note)
            except Exception:
                continue
            abbr = ""
            if hasattr(pat, "slot_abbr") and i < len(pat.slot_abbr):
                abbr = str(pat.slot_abbr[i])
            if not abbr:
                abbr = f"S{i}"
            drum_lanes.append((abbr, n))
            # Use first occurrence for note->slot mapping (avoid duplicates)
            if n not in note_to_slot:
                note_to_slot[n] = i

        # Reverse lane order for seqedit display
        drum_lanes = list(reversed(drum_lanes))
        if not drum_lanes or not note_to_slot:
            msg = "StepSeq: no SLOT notes found in this ADT"
            return

# 5) StepSeq timing meta
        loop_len_ticks = 480 * 4 * 2  # 2 bar @ 480 PPQ
        steps = 32
        step_ticks = loop_len_ticks // steps

        meta = aps_stepseq.PatternMeta(
            name=fname,
            bpm=bpm,
            channel=9,  # CH10 (0-based)
            loop_len_ticks=loop_len_ticks,
            loop_start_tick=0,
            bars=2,
        )

        # 6) pat.grid -> DrumEvent list
        #    IMPORTANT: preserve the original accent level from ADT v2.2a:
        #      level 0..3  -> representative velocity via aps_stepseq.level_to_vel()
        drum_events = []
        for step in range(steps):
            tick = meta.loop_start_tick + step * step_ticks
            row = pat.grid[step]
            for note, slot_idx in note_to_slot.items():
                if 0 <= slot_idx < len(row):
                    level = row[slot_idx]
                    try:
                        lvl_i = int(level)
                    except Exception:
                        lvl_i = 0
                    if lvl_i > 0:
                        drum_events.append(
                            aps_stepseq.DrumEvent(
                                tick=tick,
                                chan=meta.channel,
                                note=note,
                                vel=aps_stepseq.level_to_vel(lvl_i),
                                type="on",
                            )
                        )

# 7) Define the playback callback to be used by the P key
        def play_stepseq(grid, meta_inner):
            """
            Callback invoked when Space is pressed inside StepSeq.
            Play the current StepGrid once as MIDI,
            and during playback, display the current bar number (1 or 2) at the bottom of the screen.
            """
            if mido is None or not midi_port:
                return

            err = try_open_midi_output(midi_port)
            if err:
                show_warning_popup(
                    [
                        "MIDI output port could not be opened.",
                        f"Port: {midi_port}",
                        err,
                    ],
                    title="Warning",
                )
                return

            try:
                # StepGrid -> DrumEvent list (no non_grid events)
                events = aps_stepseq._apply_stepgrid_to_events(
                    grid,
                    meta_inner,
                    [],  # No non_grid_events
                )

                # Tick → time conversion
                ticks_per_quarter = 480.0
                sec_per_quarter = 60.0 / float(meta_inner.bpm)
                sec_per_tick = sec_per_quarter / ticks_per_quarter

                import time as _time

                # Compute bar boundaries based on a 2-bar pattern
                loop_len = meta_inner.loop_len_ticks
                half_loop = loop_len // 2 if loop_len > 0 else 1

                def show_bar_label(bar_no: int):
                    # Display in large text at the bottom of the grid
                    max_y, max_x = stdscr.getmaxyx()
                    text = f" PLAYING BAR {bar_no} "
                    y = max_y - 3  # Roughly the line just above the footer
                    x = max(0, (max_x - len(text)) // 2)
                    try:
                        stdscr.addstr(y, x, text)
                        stdscr.refresh()
                    except curses.error:
                        pass

                def clear_bar_label():
                    max_y, max_x = stdscr.getmaxyx()
                    y = max_y - 3
                    try:
                        stdscr.addstr(y, 0, " " * max_x)
                        stdscr.refresh()
                    except curses.error:
                        pass

                with mido.open_output(midi_port) as port:
                    last_tick = 0
                    current_bar = None

                    for ev in events:
                        # Compute current bar from ticks (1 or 2)
                        bar = 1 if ev.tick < half_loop else 2

                        if bar != current_bar:
                            current_bar = bar
                            show_bar_label(current_bar)

                        dt_ticks = ev.tick - last_tick
                        if dt_ticks > 0:
                            _time.sleep(dt_ticks * sec_per_tick)
                        last_tick = ev.tick

                        msg_type = "note_on" if ev.type == "on" else "note_off"
                        try:
                            port.send(
                                mido.Message(
                                    msg_type,
                                    note=ev.note,
                                    velocity=ev.vel,
                                    channel=ev.chan,
                                )
                            )
                        except Exception:
                            # Ignore failures of individual events
                            pass

                # Clear the display after playback finishes
                clear_bar_label()

            except Exception:
                # Ignore playback errors so they don't kill the editing session
                pass


        # 8) Enter Step Sequencer (now P calls play_stepseq)
        modified, saved, new_events = aps_stepseq.stepseq_mode(
            stdscr,
            meta,
            drum_events,
            play_callback=play_stepseq,
            drum_lanes=drum_lanes,
        )

        # Restore main UI colors/pairs in case StepSeq modified curses state
        try:
            init_main_colors()
        except Exception:
            pass

        # 9) If nothing changed and nothing was saved, exit as-is
        if (not modified) and (not saved):
            msg = "StepSeq: 변경 없음"
            return
        # 10) Clear only drum slots in pat.grid to zeros
        for step in range(steps):
            row = pat.grid[step]
            for slot_idx in note_to_slot.values():
                if 0 <= slot_idx < len(row):
                    row[slot_idx] = 0

        # 11) Apply new DrumEvents back onto the grid (note_on only)
        for de in new_events:
            if de.type != "on" or de.chan != meta.channel:
                continue
            slot_idx = note_to_slot.get(de.note)
            if slot_idx is None:
                continue
            rel_tick = de.tick - meta.loop_start_tick
            if rel_tick < 0:
                continue
            step_f = float(rel_tick) / float(step_ticks)
            step_idx = int(round(step_f))
            if 0 <= step_idx < steps:
                row = pat.grid[step_idx]
                if 0 <= slot_idx < len(row):
                    row[slot_idx] = aps_stepseq.vel_to_level(getattr(de, 'vel', 0))

        # 12) Use the modified pattern as the preview
        loaded_pattern = pat
        loaded_pattern = pat
        if saved:
            try:
                validate_grid_levels_v22a(pat)
                write_adt_file_v22a(path, pat)
                pattern_files = scan_patterns(root)
                msg = f"StepSeq: saved {fname}"
            except Exception as e:
                msg = f"StepSeq save failed: {e}"
        else:
            msg = "StepSeq: modified (not saved)"




    while True:
        stdscr.clear()
        draw_menu(stdscr)
        # Menu bar override (F4 Info, F5 DupPat)
        try:
            max_y0, max_x0 = stdscr.getmaxyx()
            menu = "F1 Help  F2 Pat/ARR  F3 Refresh  F4 Info  F5 DupPat  F6 MIDI  F7 SaveARR  F8 CountIn  F9 BPM  q/F10 Quit"
            stdscr.addnstr(0, 0, menu.ljust(max_x0 - 1), max_x0 - 1)
        except curses.error:
            pass
        # Safety guard: if midi_port isn't set locally yet, auto-select a default
        if 'midi_port' not in locals():
            midi_port = find_gs()
        draw_status(
            stdscr,
            midi_port,
            bpm,
            mode,
            msg,
            repeat_mode,
        )
        msg = ""

        max_y, max_x = stdscr.getmaxyx()
        work_top = 1
        work_height = max_y - 2

        list_w = max_x // 3
        right_w = max_x - list_w - 1
        right_h = work_height

        # Choose grid preview height tightly so that it leaves at most 2 blank rows,
        # giving the rest of the space to the ARR (chain) window.
        slots_preview = 12
        try:
            if loaded_pattern is not None:
                if hasattr(loaded_pattern, "slot_abbr") and loaded_pattern.slot_abbr:
                    slots_preview = len(loaded_pattern.slot_abbr)
                elif hasattr(loaded_pattern, "slots") and int(loaded_pattern.slots) > 0:
                    slots_preview = int(loaded_pattern.slots)
        except Exception:
            slots_preview = 12

        # Heuristic: draw_grid typically needs a small header + one row per slot.
        # Keep two extra blank rows for readability.
        min_grid_h = max(6, slots_preview + 5)
        grid_h = min(min_grid_h, right_h - 3)
        if grid_h < 6:
            grid_h = 6

        chain_h = right_h - grid_h
        if chain_h < 3:
            chain_h = 3
            grid_h = right_h - chain_h

        # Decide current left list (pattern / ARR)
        current_list = arr_files if list_mode == "arr" else pattern_files

        # Pattern / ARR list window
        list_win = stdscr.derwin(work_height, list_w, work_top, 0)
        list_win.box()

        # Title depends on focus + mode
        mode_tag = "PAT" if list_mode == "patterns" else "ARR"
        if focus == "patterns":
            title = f" ▶ {mode_tag} List "
            title_attr = curses.A_BOLD
        else:
            title = f"   {mode_tag} List "
            title_attr = 0
        try:
            if title_attr:
                list_win.attron(title_attr)
            list_win.addstr(0, 2, title[: list_w - 4])
            if title_attr:
                list_win.attroff(title_attr)
        except curses.error:
            pass

        list_h, list_w2 = list_win.getmaxyx()
        inner = list_h - 2                 # Number of visible "rows" on screen
        col_w = (list_w2 - 2) // 2
        total = len(current_list)

        # If top_index is pushed too far back, clamp it
        if total > 0:
            max_top = max(0, total - 1)
            if top_index > max_top:
                top_index = max_top
            if top_index < 0:
                top_index = 0
        else:
            top_index = 0

        # --- Render 2-column list ---
        for sr in range(inner):
            y = 1 + sr
            if y >= list_h - 1:
                break

            row_index = top_index + sr
            left_idx = row_index
            right_idx = row_index + inner

            def get_ab_marker(idx: int) -> str:
                if list_mode != "patterns":
                    return " "
                if idx not in bar_sources:
                    return " "
                if len(bar_sources) >= 2:
                    return "A" if idx == bar_sources[0] else "B"
                else:
                    return "A"

            def draw_cell(idx: int, x: int):
                if not (0 <= idx < total):
                    try:
                        list_win.addstr(y, x, " " * col_w)
                    except curses.error:
                        pass
                    return

                f_name = current_list[idx]
                marker = get_ab_marker(idx)
                tx = f"{marker}{idx+1:02d} {f_name}"
                seg = tx[:col_w].ljust(col_w)

                is_selected = (idx == selected_idx)
                is_ab = (list_mode == "patterns" and idx in bar_sources)

                if is_selected:
                    if focus == "patterns":
                        attr = curses.A_REVERSE | curses.A_BOLD
                    else:
                        attr = curses.A_BOLD
                        if highlight_unfocused_pair and use_color:
                            attr |= curses.color_pair(highlight_unfocused_pair)
                    if is_ab and focus != "patterns" and use_color and highlight_unfocused_pair:
                        attr |= curses.color_pair(highlight_unfocused_pair)
                    try:
                        list_win.attron(attr)
                        list_win.addstr(y, x, seg)
                        list_win.attroff(attr)
                    except curses.error:
                        pass
                else:
                    if is_ab and use_color and highlight_unfocused_pair:
                        attr = curses.color_pair(highlight_unfocused_pair)
                        try:
                            list_win.attron(attr)
                            list_win.addstr(y, x, seg)
                            list_win.attroff(attr)
                        except curses.error:
                            pass
                    else:
                        try:
                            list_win.addstr(y, x, seg)
                        except curses.error:
                            pass

            draw_cell(left_idx, 1)
            draw_cell(right_idx, 1 + col_w)

        list_win.refresh()

        grid_win = stdscr.derwin(grid_h, right_w, work_top, list_w + 1)
        draw_grid(loaded_pattern, grid_win, None, use_color, color_pairs)
####
        # In composite preview, show A/B pattern names and mode
        if composite_mode and len(bar_sources) == 2:
            try:
                a_idx, b_idx = bar_sources[0], bar_sources[1]
                a_name = (
                    pattern_files[a_idx]
                    if 0 <= a_idx < len(pattern_files)
                    else "?"
                )
                b_name = (
                    pattern_files[b_idx]
                    if 0 <= b_idx < len(pattern_files)
                    else "?"
                )
                mode_str = "A1 + B2" if not composite_swap else "B1 + A2"
                gh, gw = grid_win.getmaxyx()

                # Cap the display to avoid shifting too far to the right
                # Grid usually uses the left 0..~gw*0.75; use only the remaining ~25% space
                MAX_X = int(gw * 0.75)

                def place_line(y, text):
                    x = MAX_X - len(text)
                    if x < 2:
                        x = 2
                    grid_win.addstr(y, x, text[: max(0, gw - x - 1)])

                if gh > 0:
                    place_line(0, f"Composite: {mode_str}")
                if gh > 1:
                    place_line(1, f"A = {a_name}")
                if gh > 2:
                    place_line(2, f"B = {b_name}")

            except curses.error:
                pass

####
        chain_win = stdscr.derwin(
            chain_h, right_w, work_top + grid_h, list_w + 1
        )
        draw_chain_view(
            chain_win,
            chain,
            len(chain),
            focus == "chain",
            chain_selected_idx,
            selection,
            section_mgr,
            get_countin_label(),
        )

#        stdscr.refresh()

        ch = stdscr.getch()
        # --- terminal resize handling ---
        if ch == curses.KEY_RESIZE:
            try:
                # Refresh curses' idea of screen size
                curses.update_lines_cols()
            except Exception:
                pass

            try:
                h, w = stdscr.getmaxyx()
                # Tell curses to resize internal structures
                curses.resizeterm(h, w)
            except Exception:
                pass

            # Force full redraw on next iteration
            stdscr.erase()
            stdscr.refresh()
            continue
        
        

        # --- Helper: adjust scroll so the selected index is visible ---
        def ensure_visible(total_len: int):
            nonlocal top_index, selected_idx, inner
            if inner <= 0 or total_len <= 0:
                top_index = 0
                return
            visible_cap = inner * 2
            if selected_idx < top_index:
                top_index = selected_idx
            elif selected_idx >= top_index + visible_cap:
                top_index = selected_idx - visible_cap + 1
            max_top_local = max(0, total_len - 1)
            if top_index > max_top_local:
                top_index = max_top_local
            if top_index < 0:
                top_index = 0

        # --- Helper: show multi-line text in a centered reverse-video popup ---
        def show_text_popup(lines_to_show: List[str], title: str = "Info"):
            nonlocal stdscr
            max_y, max_x = stdscr.getmaxyx()
            # Compute width/height including margins
            content = [ln.rstrip("\n") for ln in lines_to_show]
            if not content:
                content = ["(empty)"]
            w = min(max_x - 4, max(20, min(max(len(ln) for ln in content) + 4, max_x - 4)))
            h = min(max_y - 4, max(6, min(len(content) + 4, max_y - 4)))
            y0 = (max_y - h) // 2
            x0 = (max_x - w) // 2
            try:
                win = curses.newwin(h, w, y0, x0)
                win.bkgd(" ", curses.A_REVERSE)
                win.erase()
                win.border()
                if title:
                    t = f" {title} "
                    if len(t) < w - 2:
                        win.addnstr(0, max(1, (w - len(t)) // 2), t, w - 2, curses.A_REVERSE)
                # Number of displayable lines
                cap = h - 4
                for i, ln in enumerate(content[:cap]):
                    win.addnstr(2 + i, 2, ln.ljust(w - 4), w - 4, curses.A_REVERSE)
                hint = "Press any key to dismiss"
                if len(hint) < w - 4:
                    win.addnstr(h - 2, w - len(hint) - 2, hint, len(hint), curses.A_REVERSE)
                win.refresh()
                win.getch()
            except curses.error:
                # Fallback: show as a status message
                show_message(stdscr, f"{title}: " + (content[0] if content else ""), 2.0)

        # --- F5: duplicate the selected pattern into the 9xx range ---

        def show_text_viewer(lines_to_show: List[str], title: str = "View"):
            """Scrollable read-only text viewer (reverse style)."""
            max_y, max_x = stdscr.getmaxyx()
            content = [ln.rstrip("\n") for ln in (lines_to_show or [])]
            if not content:
                content = ["(empty)"]

            w = min(max_x - 2, max(30, max_x - 6))
            h = min(max_y - 2, max(10, max_y - 6))
            y0 = (max_y - h) // 2
            x0 = (max_x - w) // 2

            offset = 0
            cap = h - 4

            try:
                win = curses.newwin(h, w, y0, x0)
                win.keypad(True)
                win.bkgd(" ", curses.A_REVERSE)

                while True:
                    win.erase()
                    win.border()

                    if title:
                        t = f" {title} "
                        if len(t) < w - 2:
                            win.addnstr(0, max(1, (w - len(t)) // 2), t, w - 2, curses.A_REVERSE)

                    max_off = max(0, len(content) - cap)
                    offset = max(0, min(offset, max_off))

                    for i in range(cap):
                        idx = offset + i
                        if idx >= len(content):
                            break
                        ln = content[idx]
                        win.addnstr(2 + i, 2, ln.ljust(w - 4), w - 4, curses.A_REVERSE)

                    hint = "↑↓ PgUp PgDn: scroll  q/ESC: close"
                    if len(hint) < w - 4:
                        win.addnstr(h - 2, w - len(hint) - 2, hint, len(hint), curses.A_REVERSE)

                    win.refresh()
                    k = win.getch()

                    if k in (27, ord("q"), ord("Q")):
                        break
                    elif k in (curses.KEY_UP, ord("k"), ord("K")):
                        offset -= 1
                    elif k in (curses.KEY_DOWN, ord("j"), ord("J")):
                        offset += 1
                    elif k == curses.KEY_PPAGE:
                        offset -= cap
                    elif k == curses.KEY_NPAGE:
                        offset += cap
                    elif k == curses.KEY_HOME:
                        offset = 0
                    elif k == curses.KEY_END:
                        offset = len(content)
            except curses.error:
                show_message(stdscr, f"{title}: " + (content[0] if content else ""), 2.0)

        def duplicate_selected_pattern():
            nonlocal pattern_files, selected_idx, list_mode, msg
            if list_mode != "patterns" or not pattern_files:
                return
            src_name = pattern_files[selected_idx]
            base, ext = os.path.splitext(src_name)
            if len(base) < 3:
                msg = "DupPat failed: bad pattern name"
                return
            genre = base[:3]
            # Search for an empty slot starting from 901
            for n in range(901, 999):
                dst_base = f"{genre}_P{n:03d}"
                dst_name = dst_base + ext
                dst_path = os.path.join(root, dst_name)
                if not os.path.exists(dst_path):
                    # Copy file (binary)
                    try:
                        with open(os.path.join(root, src_name), "rb") as fsrc:
                            data = fsrc.read()
                        with open(dst_path, "wb") as fdst:
                            fdst.write(data)
                        # Refresh list and select the new file
                        pattern_files = scan_patterns(root)
                        if dst_name in pattern_files:
                            selected_idx = pattern_files.index(dst_name)
                        msg = f"DupPat: {src_name} -> {dst_name}"
                    except Exception as e:
                        msg = f"DupPat failed: {e}"
                    return
            msg = "DupPat failed: no free slot 901-999"


        # Quit (q / F10) - no Enter required
        if ch in (ord("q"), curses.KEY_F10):
            try:
                ok = dialog_confirm(
                    stdscr,
                    "Quit APS?",
                    yes_label="YES",
                    no_label="NO",
                    default_yes=False,
                )
                if ok:
                    break
                msg = "Quit canceled."
                continue
            except Exception:
                # Fallback: legacy inline prompt
                max_yq, max_xq = stdscr.getmaxyx()
                msg_text = "Quit APS? (y/q = yes, other = no)"
                yq = max_yq // 2
                xq = max(0, (max_xq - len(msg_text)) // 2)
                try:
                    stdscr.addnstr(yq, xq, msg_text, len(msg_text), curses.A_REVERSE)
                except curses.error:
                    pass
                stdscr.refresh()
                kq = stdscr.getch()
                if kq in (ord("y"), ord("Y"), ord("q"), ord("Q")):
                    break  # exit program
                else:
                    msg = "Quit canceled."
                    continue  # keep running

        # Ctrl+Z: Undo
        if ch == 26:  # ASCII SUB
            if undo_stack:
                (
                    prev_chain,
                    prev_idx,
                    prev_sel,
                    prev_secs,
                    prev_bpm,
                ) = undo_stack.pop()
                chain = prev_chain
                chain_selected_idx = prev_idx
                selection = prev_sel
                section_mgr = prev_secs
                bpm = prev_bpm
                msg = "Undo"
            else:
                msg = "Nothing to undo"
            continue

        # F1: Help
        if ch == curses.KEY_F1:
            show_help_curses(stdscr)
            continue
            
        # H/h: open the latest keymap markdown (APS_Keymap*.md)
        if ch in (ord("H"), ord("h")):
            try:
                import glob

                candidates = []
                search_dirs = []

                # Prefer the runtime root (used elsewhere), but also try the current
                # working directory and the script directory.
                try:
                    if root:
                        search_dirs.append(root)
                except Exception:
                    pass

                search_dirs.append(os.getcwd())
                search_dirs.append(os.path.dirname(__file__))
                search_dirs.append(os.path.join(os.getcwd(), "docs"))

                seen = set()
                for d in search_dirs:
                    try:
                        d = os.path.abspath(d)
                        if d in seen:
                            continue
                        seen.add(d)
                        candidates.extend(glob.glob(os.path.join(d, "APS_Keymap*.md")))
                    except Exception:
                        pass

                if not candidates:
                    msg = (
                        "No APS_Keymap*.md found. "
                        "(searched: project root, cwd, script dir, ./docs)"
                    )
                    continue

                candidates.sort(key=lambda p: os.path.getmtime(p))
                path = candidates[-1]
                fn = os.path.basename(path)

                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().splitlines()
                show_text_viewer(content, title=f"Keymap: {fn}")
            except Exception as e:
                msg = f"Keymap open error: {e}"
            continue


        # F2: toggle Pat/ARR list + refresh
        if ch == curses.KEY_F2:
            pattern_files = scan_patterns(root)
            arr_files = sorted(
                f for f in os.listdir(root) if f.lower().endswith(".arr")
            )
            if list_mode == "patterns":
                list_mode = "arr"
                current_list = arr_files
                if not current_list:
                    selected_idx = 0
                    top_index = 0
                    loaded_pattern = None
                    msg = "ARR list: (no files)"
                else:
                    selected_idx = 0
                    top_index = 0
                    loaded_pattern = None
                    msg = "ARR list"
            else:
                list_mode = "patterns"
                current_list = pattern_files
                if not current_list:
                    selected_idx = 0
                    top_index = 0
                    loaded_pattern = None
                    msg = "Pattern list: (no files)"
                else:
                    selected_idx = 0
                    top_index = 0
                    load_preview()
                    msg = "Pattern list"
            continue

        # F3: refresh (keep current mode, rescan directory)
        if ch == curses.KEY_F3:
            pattern_files = scan_patterns(root)
            arr_files = sorted(
                f for f in os.listdir(root) if f.lower().endswith(".arr")
            )
            current_list = arr_files if list_mode == "arr" else pattern_files
            total = len(current_list)
            if total == 0:
                selected_idx = 0
                top_index = 0
                loaded_pattern = None
                msg = "Refreshed (empty list)"
            else:
                if selected_idx >= total:
                    selected_idx = total - 1
                ensure_visible(total)
                if list_mode == "patterns":
                    load_preview()
                msg = "Refreshed"
            continue



        # F4: View (left pane = file content, chain pane = current ARR text)
        if ch == curses.KEY_F4:
            def _read_text_file(p: str) -> List[str]:
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        return [ln.rstrip("\n") for ln in f]
                except Exception as e:
                    return [f"(failed to open: {p})", str(e)]

            # Left pane: show raw file content (PAT/ARR list)
            if focus == "patterns":
                if list_mode == "patterns":
                    if pattern_files and 0 <= selected_idx < len(pattern_files):
                        fn = pattern_files[selected_idx]
                        ext = os.path.splitext(fn)[1].lower()
                        p = os.path.join(root, fn)
                        if ext in (".adt", ".arr", ".txt", ".md", ".pat"):
                            show_text_viewer(_read_text_file(p), title=f"FILE: {fn}")
                        elif ext in (".adp",):
                            show_text_viewer([f"{fn}", "(binary ADP file)", f"path: {p}"], title="FILE (binary)")
                        else:
                            # try text anyway
                            show_text_viewer(_read_text_file(p), title=f"FILE: {fn}")
                    else:
                        show_text_viewer(["(no pattern selected)"], title="FILE")
                else:  # list_mode == "arr"
                    if arr_files and 0 <= selected_idx < len(arr_files):
                        fn = arr_files[selected_idx]
                        p = os.path.join(root, fn)
                        show_text_viewer(_read_text_file(p), title=f"ARR FILE: {fn}")
                    else:
                        show_text_viewer(["(no ARR selected)"], title="ARR FILE")
                continue

            # Chain pane: show current in-memory state serialized as ARR text
            if focus == "chain":
                if not chain:
                    show_text_viewer(["(chain is empty)"], title="CURRENT ARR (preview)")
                    continue

                ci_label = get_countin_label()
                if ci_label in (None, "None"):
                    header_lines = ["#COUNTIN NONE"]
                else:
                    header_lines = [f"#COUNTIN {ci_label}"]

                # Build SECTION blocks from in-memory chain labels (1-based, inclusive)
                section_lines: List[str] = []
                cur_sec = None
                sec_start = 1
                for i, e in enumerate(chain, start=1):
                    sec = getattr(e, "section", None)
                    if sec != cur_sec:
                        if cur_sec:
                            section_lines.append(f"#SECTION {cur_sec} {sec_start} {i-1}")
                        cur_sec = sec
                        sec_start = i
                if cur_sec:
                    section_lines.append(f"#SECTION {cur_sec} {sec_start} {len(chain)}")

                # Build POOL and MAIN (same spirit as aps_arr.save_arr)
                pool: List[str] = []
                pool_map: dict[str, int] = {}
                seq_tokens: List[str] = []

                for e in chain:
                    fn = getattr(e, "filename", "")
                    rep = int(getattr(e, "repeats", 1) or 1)
                    if fn not in pool_map:
                        pool.append(fn)
                        pool_map[fn] = len(pool)
                    idx = pool_map[fn]
                    for _ in range(rep):
                        seq_tokens.append(str(idx))

                # Derive #PLAY (informational; sections + bare patterns)
                play_lines: List[str] = []
                last_sec = None
                in_section = False
                for e in chain:
                    sec = getattr(e, "section", None)
                    if sec:
                        if sec != last_sec:
                            play_lines.append(sec)
                            last_sec = sec
                        in_section = True
                    else:
                        # If a section label is present, do not emit per-pattern indices for that section in #PLAY.
                        if not in_section:
                            idx = pool_map.get(getattr(e, "filename", ""), None)
                            rep = int(getattr(e, "repeats", 1) or 1)
                            if idx is not None:
                                play_lines.append(f"{idx}x{rep}" if rep > 1 else f"{idx}")
                        last_sec = None

                out_lines: List[str] = []
                out_lines.extend(header_lines)
                out_lines.extend(section_lines)
                out_lines.append("#APS ARR v0.05")
                out_lines.append("")
                out_lines.append(f"BPM={bpm}")
                out_lines.append("")
                for i, fn in enumerate(pool, start=1):
                    out_lines.append(f"{i}={fn}")
                out_lines.append("")
                if play_lines:
                    out_lines.append("#PLAY")
                    out_lines.extend(play_lines)
                    out_lines.append("#ENDPLAY")
                    out_lines.append("")
                out_lines.append("MAIN|" + ",".join(seq_tokens))

                show_text_viewer(out_lines, title="CURRENT ARR (preview)")
                continue

        # F5: DupPat (duplicate selected pattern into 9xx)
        if ch == curses.KEY_F5:
            duplicate_selected_pattern()
            continue

            if loaded_pattern:
                show_pattern_info_curses(stdscr, loaded_pattern)
            continue

        # F6: select MIDI port
        if ch == curses.KEY_F6:
            name = choose_midi_port_curses(stdscr)
            if name:
                midi_port = name
            continue

        # F7: save
        # - In composite mode (composite_mode=True), save the pattern as HYB_P9xx.APT
        # - Otherwise, save ARR in the current working directory (legacy behavior)
        if ch in (curses.KEY_F7, ord('w'), ord('W')):
            if composite_mode and composite_pattern is not None:
                save_composite_pattern()
                continue

            # When saving ARR: if ADP is mixed in, write .ADT in ARR and show a message
            if not chain:
                try:
                    dialog_alert(stdscr, "Chain is empty.")
                except Exception:
                    pass
                msg = "Chain is empty."
                continue

            ok = dialog_confirm(
                stdscr,
                "Save ARR file?",
                yes_label="SAVE",
                no_label="CANCEL",
                default_yes=True,
            )
            if not ok:
                msg = "Save canceled."
                continue

            # ARR filename: re-prompt if empty or already exists
            base = None
            while True:
                base = dialog_input(
                    stdscr,
                    "ARR filename:",
                    default_text="",
                    maxlen=64,
                    suffix=".ARR",
                )
                if base is None:
                    msg = "Save canceled."
                    break

                base = base.strip()
                if not base:
                    try:
                        dialog_alert(stdscr, "Filename is empty.")
                    except Exception:
                        pass
                    continue

                arr_filename = base + ".ARR"
                path = os.path.join(root, arr_filename)

                if os.path.exists(path):
                    try:
                        dialog_alert(
                            stdscr,
                            f"File already exists:\n{arr_filename}\n\nPlease enter a different name.",
                        )
                    except Exception:
                        pass
                    continue

                # OK
                break

            if base is None:
                # canceled
                continue

            try:
                # Save a converted copy reflecting ADP → ADT conversion
                chain_for_save = [ChainEntry(e.filename, e.repeats) for e in chain]
                had_adp = False
                for e in chain_for_save:
                    if e.filename.lower().endswith(".adp"):
                        had_adp = True
                        b0, _ext0 = os.path.splitext(e.filename)
                        e.filename = b0 + ".ADT"

                # First, write the base ARR
                save_arr(path, chain_for_save, bpm)

                # Then insert #COUNTIN / #SECTION headers to record state
                try:
                    import re  # local: used for parsing pool lines
                    # Re-open the just-saved ARR and rewrite headers while preserving body.
                    # Also (re)generate #PLAY metadata so it is not lost on save.
                    old_lines: List[str] = []
                    in_play = False
                    with open(path, "r", encoding="utf-8", errors="ignore") as f:
                        for raw in f:
                            line = raw.rstrip("\n")
                            if in_play:
                                if line.strip().upper() == "#ENDPLAY":
                                    in_play = False
                                continue
                            if line.strip().upper() == "#PLAY":
                                in_play = True
                                continue
                            if line.startswith("#COUNTIN") or line.startswith("#SECTION"):
                                continue
                            old_lines.append(line)

                    ci_label = get_countin_label()
                    if ci_label in (None, "None"):
                        header = "#COUNTIN NONE"
                    else:
                        header = f"#COUNTIN {ci_label}"

                    # derive section blocks from in-memory chain labels
                    section_blocks = []
                    cur_sec = None
                    sec_start = 0
                    for i, e in enumerate(chain):
                        sec = getattr(e, "section", None)
                        if sec != cur_sec:
                            if cur_sec:
                                section_blocks.append((cur_sec, sec_start, i - 1))
                            cur_sec = sec
                            sec_start = i
                    if cur_sec:
                        section_blocks.append((cur_sec, sec_start, len(chain) - 1))

                    # Build a filename -> pool index map from the saved body (preferred),
                    # falling back to the in-memory chain order.
                    pool_map = {}
                    for ln in old_lines:
                        m = re.match(r"^(\d+)=(.+)$", ln.strip())
                        if m:
                            try:
                                idx = int(m.group(1))
                            except Exception:
                                continue
                            fn = m.group(2).strip()
                            if fn and fn not in pool_map:
                                pool_map[fn] = idx
                    if not pool_map:
                        for e in chain_for_save:
                            fn = getattr(e, "filename", "")
                            if fn and fn not in pool_map:
                                pool_map[fn] = len(pool_map) + 1

                    # Derive #PLAY lines (metadata only)
                    # Build #PLAY metadata using the in-memory chain so section labels are preserved.
                    # Note: #PLAY is metadata only; playback is driven by MAIN|...
                    play_lines: List[str] = []
                    last_sec = None
                    in_section = False
                    for e in chain:
                        sec = getattr(e, "section", None)
                        if sec:
                            if sec != last_sec:
                                play_lines.append(str(sec))
                                last_sec = sec
                            # If a section label is present, do not emit per-pattern indices for that section in #PLAY.
                            continue

                        # No section: emit pool index token
                        last_sec = None
                        fn = getattr(e, "filename", "")
                        if fn.lower().endswith(".adp"):
                            b0, _ext0 = os.path.splitext(fn)
                            fn = b0 + ".ADT"
                        idx = pool_map.get(fn)
                        rep = int(getattr(e, "repeats", 1) or 1)
                        if idx is None:
                            continue
                        play_lines.append(f"{idx}x{rep}" if rep > 1 else f"{idx}")
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(header + "\n")
                        for sec, s2, e2 in section_blocks:
                            f.write(f"#SECTION {sec} {s2+1} {e2+1}\n")
                        if play_lines:
                            f.write("#PLAY\n")
                            for pl in play_lines:
                                f.write(pl + "\n")
                            f.write("#ENDPLAY\n")
                        prev_blank = False
                        for ln in old_lines:
                            s = ln.strip()
                            # Normalize version tag line
                            if s.startswith("# APS ARR") or s.startswith("#APS ARR"):
                                f.write("#APS ARR v0.05\n")
                                prev_blank = False
                                continue

                            # Ensure one blank line right before BPM=
                            if s.startswith("BPM=") and not prev_blank:
                                f.write("\n")
                                prev_blank = True

                            f.write(ln + "\n")
                            prev_blank = (s == "")
                except Exception:
                    # Even if header insertion fails, keep the base ARR; ignore quietly
                    pass

                if had_adp:
                    msg = f"Saved {arr_filename} (ADP → ADT in ARR)"
                else:
                    msg = f"Saved {arr_filename}"
            except Exception as e:
                msg = str(e)
            continue
        # F8: choose Count-in
        if ch == curses.KEY_F8:
            new_idx = choose_countin_curses(stdscr, countin_idx)
            if new_idx is not None:
                countin_idx = new_idx  # -1 = None, 0..N-1 = preset
            continue

        # F9: change BPM
        if ch == curses.KEY_F9:
            s = dialog_input(stdscr, f"BPM (current {bpm}):", default_text=str(bpm), maxlen=6)
            if s is None:
                # canceled
                continue
            try:
                v = int(s)
                if v > 0:
                    push_undo()
                    bpm = v
            except Exception:
                pass
            continue

        # Toggle focus (Tab)
        if ch == ord("\t"):
            focus = "chain" if focus == "patterns" else "patterns"
            continue

        # Chain focus: move/repeat/delete/define sections, etc. (includes block editing)
        if focus == "chain":
            # ESC: clear block selection
            if ch == 27:  # ESC
                if selection.get_range():
                    selection.reset()
                    msg = "Selection cleared"
                continue

            # When chain window has focus, Enter does not insert a pattern
            if ch in (10, 13):  # Enter
                continue

            rng = selection.get_range()

            # 1) Delete: delete block (delete the entire selected range)
            if ch == curses.KEY_DC and rng and chain:
                push_undo()
                start, end = rng
                if start < 0:
                    start = 0
                if end >= len(chain):
                    end = len(chain) - 1
                del_count = end - start + 1
                del chain[start : end + 1]
                selection.reset()
                if chain:
                    chain_selected_idx = min(start, len(chain) - 1)
                else:
                    chain_selected_idx = 0
                msg = f"Deleted {del_count} step(s)"
                continue

            # 2) x / X: cut block
            if ch in (ord("x"), ord("X")) and rng and chain:
                push_undo()
                start, end = rng
                if start < 0:
                    start = 0
                if end >= len(chain):
                    end = len(chain) - 1
                clipboard = [
                    ChainEntry(e.filename, e.repeats)
                    for e in chain[start : end + 1]
                ]
                del_count = end - start + 1
                del chain[start : end + 1]
                selection.reset()
                if chain:
                    chain_selected_idx = min(start, len(chain) - 1)
                else:
                    chain_selected_idx = 0
                msg = f"Cut {del_count} step(s)"
                continue

            # 3) y / Y: copy block
            if ch in (ord("y"), ord("Y")) and rng and chain:
                start, end = rng
                if start < 0:
                    start = 0
                if end >= len(chain):
                    end = len(chain) - 1
                clipboard = [
                    ChainEntry(e.filename, e.repeats)
                    for e in chain[start : end + 1]
                ]
                msg = f"Copied {len(clipboard)} step(s)"
                selection.reset()
                continue

            # 4) p / P: paste (choose from clipboard/section, then choose above/below position)
            if ch in (ord("p"), ord("P")):
                choice = choose_block_or_section_curses(
                    stdscr, clipboard, section_mgr, chain
                )
                if not choice:
                    continue
                entries_to_paste, label = choice
                pos = choose_paste_position_curses(stdscr)
                if not pos:
                    continue

                if not entries_to_paste:
                    continue

                if not chain:
                    insert_at = 0
                else:
                    if (
                        chain_selected_idx < 0
                        or chain_selected_idx >= len(chain)
                    ):
                        chain_selected_idx = len(chain) - 1
                    insert_at = (
                        chain_selected_idx
                        if pos == "before"
                        else chain_selected_idx + 1
                    )

                push_undo()
                
                for i, e in enumerate(entries_to_paste):
                    chain.insert(insert_at + i, e)
                section_mgr.split_for_insert(insert_at, len(entries_to_paste))
                _sync_chain_section_labels_from_mgr()
                chain_selected_idx = insert_at
            
                selection.reset()
                msg = f"Pasted {len(entries_to_paste)} step(s) from {label}"
                continue

                        # R/r: remove the section at the current cursor (chain focus only)
            # - This restores the previous behavior that was shadowed by repeat_mode toggle.
            if ch in (ord("r"), ord("R")) and chain:
                cur = chain_selected_idx
                if 0 <= cur < len(chain):
                    sec = getattr(chain[cur], "section", None)
                    if sec:
                        push_undo()
                        section_mgr.remove_section(sec)
                        _sync_chain_section_labels_from_mgr()
                        msg = f"Section '{sec}' removed"
                continue

# Default handling for chain keys (move, single-line delete/repeat, O/o, etc.)
            chain_selected_idx, changed = handle_chain_keys(
                ch,
                chain,
                chain_selected_idx,
                selection,
                section_mgr,
                pattern_files,
                selected_idx,
                push_undo,
            )
            if ch == ord("s"):
                rng = selection.get_range()
                if rng:
                    start, end = rng
                    name = dialog_input(stdscr, "Section name:", default_text="", maxlen=24)
                    if name is None:
                        show_message(stdscr, "Section naming canceled.")
                        selection.reset()
                        continue

                    name = name.strip()
                    if not name:
                        show_message(stdscr, "Section name is empty.")
                        selection.reset()
                        continue

                    push_undo()
                    ok = section_mgr.add_section(name, start, end)

                    if not ok:
                        suffix = 2
                        while not ok and suffix < 100:
                            alt = f"{name}_{suffix}"
                            ok = section_mgr.add_section(alt, start, end)
                            if ok:
                                name = alt
                                break
                            suffix += 1

                    if ok:
                        for i in range(start, end + 1):
                            chain[i].section = name
                        modified = True
                        msg = f"Section '{name}' added"
                    else:
                        msg = "Section overlap error"
                    show_message(stdscr, msg)
                    selection.reset()
            if ch not in (ord(" "),):
                continue

        # Pattern list focus: move selection within the pattern/ARR list
        if focus == "patterns":
            current_list = arr_files if list_mode == "arr" else pattern_files
            total = len(current_list)

            # ↑ / k: move up one item
            if ch in (curses.KEY_UP, ord("k")):
                if total > 0 and selected_idx > 0:
                    selected_idx -= 1
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # ↓ / j: move down one item
            if ch in (curses.KEY_DOWN, ord("j")):
                if total > 0 and selected_idx < total - 1:
                    selected_idx += 1
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # ← / h: right column → left column
            if ch in (curses.KEY_LEFT, ord("h")) and inner > 0:
                if total > 0:
                    visible_cap = inner * 2
                    offset = selected_idx - top_index
                    if 0 <= offset < visible_cap:
                        if offset >= inner:
                            new_idx = selected_idx - inner
                            if new_idx >= 0:
                                selected_idx = new_idx
                                ensure_visible(total)
                                if list_mode == "patterns":
                                    load_preview()
                continue

            # → / l: left column → right column
            if ch in (curses.KEY_RIGHT, ord("l")) and inner > 0:
                if total > 0:
                    visible_cap = inner * 2
                    offset = selected_idx - top_index
                    if 0 <= offset < visible_cap:
                        if offset < inner:
                            new_idx = selected_idx + inner
                            if new_idx < total:
                                selected_idx = new_idx
                                ensure_visible(total)
                                if list_mode == "patterns":
                                    load_preview()
                continue

            # PageUp
            if ch == curses.KEY_PPAGE:
                if total > 0:
                    page_size = max(1, inner * 2)
                    selected_idx = max(0, selected_idx - page_size)
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # PageDown
            if ch == curses.KEY_NPAGE:
                if total > 0:
                    page_size = max(1, inner * 2)
                    selected_idx = min(total - 1, selected_idx + page_size)
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # 'b'
            if list_mode == "patterns" and ch == ord("b"):
                if total > 0 and 0 <= selected_idx < total:
                    if selected_idx in bar_sources:
                        bar_sources.remove(selected_idx)
                    else:
                        bar_sources.append(selected_idx)
                        if len(bar_sources) > 2:
                            bar_sources.pop(0)
                composite_mode = False
                composite_pattern = None
                composite_swap = False
                continue

            # 's' / 'S': enter Step Sequencer
            if list_mode == "patterns" and ch in (ord("s"), ord("S")):
                open_stepseq_for_selected_pattern()
                if list_mode == "patterns":
                    load_preview()
                continue


            # 'B'
            if list_mode == "patterns" and ch == ord("B"):
                if len(bar_sources) == 2:
                    if not composite_mode:
                        composite_swap = False
                    else:
                        composite_swap = not composite_swap
                    rebuild_composite()
                else:
                    msg = "A/B로 사용할 패턴 두 개를 먼저 'b'로 선택하세요."
                continue

            # ESC: clear composite preview/selection
            if ch == 27:  # ESC
                if composite_mode:
                    composite_mode = False
                    composite_pattern = None
                    composite_swap = False
                    if list_mode == "patterns":
                        load_preview()
                elif bar_sources:
                    bar_sources = []
                else:
                    pass
                continue

        # ===== Common behaviors =====

        # Enter: insert into chain
        if focus == "patterns" and ch in (10, 13):
            if list_mode == "patterns":
                if pattern_files:
                    push_undo()
                    fn = pattern_files[selected_idx]
                    if not chain:
                        chain.append(ChainEntry(fn, 1))
                        chain_selected_idx = 0
                    else:
                        if chain_selected_idx < 0 or chain_selected_idx >= len(chain):
                            chain_selected_idx = len(chain) - 1

                        cur = chain[chain_selected_idx]

                        if cur.filename == fn:
                            cur.repeats += 1
                        else:
                            insert_at = chain_selected_idx + 1
                            if (
                                insert_at < len(chain)
                                and chain[insert_at].filename == fn
                            ):
                                chain[insert_at].repeats += 1
                                chain_selected_idx = insert_at
                            else:
                                chain.insert(insert_at, ChainEntry(fn, 1))
                                section_mgr.split_for_insert(insert_at, 1)
                                _sync_chain_section_labels_from_mgr()
                                chain_selected_idx = insert_at

            else:
                if arr_files:
                    arr_name = arr_files[selected_idx]
                    arr_path = os.path.join(root, arr_name)
                    try:
                        load_countin_from_arr(arr_path)
                        parsed = parse_arr(arr_path)

                        # Backward compatible: parse_arr may return (chain, bpm)
                        # or (chain, bpm, sections).
                        arr_sections = {}
                        if isinstance(parsed, tuple) and len(parsed) >= 3:
                            arr_chain, _arr_bpm, arr_sections = parsed[0], parsed[1], (parsed[2] or {})
                        elif isinstance(parsed, tuple) and len(parsed) >= 2:
                            arr_chain, _arr_bpm = parsed[0], parsed[1]
                        else:
                            arr_chain, _arr_bpm = parsed, None

                        if not arr_chain:
                            msg = "ARR is empty"
                        else:
                            push_undo()
                            block = [
                                ChainEntry(e.filename, e.repeats)
                                for e in arr_chain
                            ]
                            if not chain:
                                chain = block
                                chain_selected_idx = 0
                                # Apply imported ARR sections for a fresh chain
                                section_mgr.import_sections_from_source(arr_sections, 0, prefix="i_")
                                _sync_chain_section_labels_from_mgr()
                            else:
                                if (
                                    chain_selected_idx < 0
                                    or chain_selected_idx >= len(chain)
                                ):
                                    chain_selected_idx = len(chain) - 1
                                insert_at = chain_selected_idx + 1
                                for i, e in enumerate(block):
                                    chain.insert(insert_at + i, e)
                                section_mgr.split_for_insert(insert_at, len(block))

                                section_mgr.import_sections_from_source(arr_sections, insert_at, prefix="i_")

                                _sync_chain_section_labels_from_mgr()
                                chain_selected_idx = insert_at
                            msg = f"Inserted ARR '{arr_name}' ({len(block)} steps)"
                    except Exception as e:
                        msg = f"ARR insert error: {e}"
            continue

        # Shift+O
        # O/o: insert BEFORE the current chain cursor (patterns/ARR list)
        # - Patterns list: insert selected pattern before cursor (or merge repeats when adjacent)
        # - ARR list: insert selected ARR block before cursor (and apply ARR sections with prefix)
        if ch in (ord("O"), ord("o")) and focus == "patterns":
            if list_mode == "patterns":
                if pattern_files:
                    push_undo()
                    fn = pattern_files[selected_idx]
                    if not chain:
                        chain.append(ChainEntry(fn, 1))
                        chain_selected_idx = 0
                    else:
                        if chain_selected_idx < 0 or chain_selected_idx >= len(chain):
                            chain_selected_idx = len(chain) - 1

                        cur = chain[chain_selected_idx]

                        if cur.filename == fn:
                            cur.repeats += 1
                        else:
                            insert_at = chain_selected_idx
                            if (
                                insert_at > 0
                                and chain[insert_at - 1].filename == fn
                            ):
                                chain[insert_at - 1].repeats += 1
                                chain_selected_idx = insert_at - 1
                            else:
                                chain.insert(insert_at, ChainEntry(fn, 1))
                                section_mgr.split_for_insert(insert_at, 1)
                                _sync_chain_section_labels_from_mgr()
                                chain_selected_idx = insert_at

            else:  # list_mode == "arr"
                if arr_files:
                    arr_name = arr_files[selected_idx]
                    arr_path = os.path.join(root, arr_name)
                    try:
                        load_countin_from_arr(arr_path)
                        parsed = parse_arr(arr_path)

                        # Backward compatible: parse_arr may return (chain, bpm)
                        # or (chain, bpm, sections).
                        arr_sections = {}
                        if isinstance(parsed, tuple) and len(parsed) >= 3:
                            arr_chain, _arr_bpm, arr_sections = parsed[0], parsed[1], (parsed[2] or {})
                        elif isinstance(parsed, tuple) and len(parsed) >= 2:
                            arr_chain, _arr_bpm = parsed[0], parsed[1]
                        else:
                            arr_chain, _arr_bpm = parsed, None

                        if not arr_chain:
                            msg = "ARR is empty"
                        else:
                            push_undo()
                            block = [ChainEntry(e.filename, e.repeats) for e in arr_chain]

                            if not chain:
                                chain = block
                                chain_selected_idx = 0
                                # Apply imported ARR sections for a fresh chain
                                section_mgr.import_sections_from_source(arr_sections, 0, prefix="i_")
                                _sync_chain_section_labels_from_mgr()
                            else:
                                if (
                                    chain_selected_idx < 0
                                    or chain_selected_idx >= len(chain)
                                ):
                                    chain_selected_idx = len(chain) - 1

                                insert_at = chain_selected_idx
                                for i, e in enumerate(block):
                                    chain.insert(insert_at + i, e)

                                section_mgr.split_for_insert(insert_at, len(block))
                                section_mgr.import_sections_from_source(arr_sections, insert_at, prefix="i_")
                                _sync_chain_section_labels_from_mgr()
                                chain_selected_idx = insert_at

                            msg = f"Inserted ARR '{arr_name}' ({len(block)} steps)"
                    except Exception as e:
                        msg = f"ARR insert error: {e}"
            continue

        # Space: play
        if ch == ord(" "):
            if focus == "patterns":
                if loaded_pattern and midi_port:
                    err = try_open_midi_output(midi_port)
                    if err:
                        show_warning_popup(
                            [
                                "MIDI output port could not be opened.",
                                f"Port: {midi_port}",
                                err,
                            ],
                            title="Warning",
                        )
                        mode = "VIEW"
                        continue

                    from aps_playback import play_pattern_in_grid

                    mode = "PLAY"
                    play_pattern_in_grid(
                        loaded_pattern,
                        bpm,
                        midi_port,
                        stdscr,
                        grid_win,
                        use_color,
                        color_pairs,
                        repeat_mode,
                    )
                    mode = "VIEW"
            else:
                if chain and midi_port:
                    missing = []
                    for e in chain:
                        p = os.path.join(root, e.filename)
                        if not os.path.exists(p):
                            missing.append(e.filename)
                    if missing:
                        show_warning_popup(
                            [
                                "Missing component pattern file(s) for this ARR/chain.",
                                f"First missing: {missing[0]}",
                                f"Total missing: {len(missing)}",
                            ],
                            title="Warning",
                        )
                        mode = "VIEW"
                        continue


                    err = try_open_midi_output(midi_port)
                    if err:
                        show_warning_popup(
                            [
                                "MIDI output port could not be opened.",
                                f"Port: {midi_port}",
                                err,
                            ],
                            title="Warning",
                        )
                        mode = "VIEW"
                        continue

                    from aps_playback import play_chain

                    mode = "CHAIN"

                    out_port = None
                    if (
                        mido is not None
                        and countin_idx is not None
                        and countin_idx >= 0
                        and 0 <= countin_idx < len(countin_presets)
                    ):

                        def _load(path):
                            return (
                                load_adt(path)
                                if path.lower().endswith(".adt")
                                else load_adp(path)
                            )

                        try:
                            out_port = mido.open_output(midi_port)
                            # Count-in (4 fixed hits)
                            # NOTE: keep using same out_port for main playback to avoid reopen delay.
                            note = 42  # Closed HH by default
                            vel = 100
                            ch9 = 9
                            quarter = 60.0 / float(bpm)
                            # Prefetch the first MAIN pattern to avoid a gap after count-in (warms disk/cache).
                            try:
                                _start_i = chain_selected_idx
                                if 0 <= _start_i < len(chain):
                                    _entry0 = chain[_start_i]
                                    _path0 = os.path.join(root, _entry0.filename)
                                    if os.path.isfile(_path0):
                                        load_pattern(_path0)
                            except Exception:
                                pass
                            time.sleep(min(0.05, quarter * 0.1))  # allow port/device to settle before first hit
                            on_frac = 0.35
                            off_frac = 0.65
                            for _i in range(4):
                                out_port.send(mido.Message('note_on', note=note, velocity=vel, channel=ch9))
                                time.sleep(quarter * on_frac)
                                out_port.send(mido.Message('note_off', note=note, velocity=0, channel=ch9))
                                # Wait the remaining beat so MAIN starts on the next downbeat
                                time.sleep(quarter * off_frac)

                            chain_selected_idx = play_chain(
                                chain,
                                bpm,
                                midi_port,
                                stdscr,
                                grid_win,
                                chain_win,
                                root,
                                use_color,
                                color_pairs,
                                chain_selected_idx,
                                _load,
                                out=out_port,
                            )
                            try:
                                out_port.close()
                            except Exception:
                                pass
                        except Exception as e:
                            show_warning_popup(
                                [
                                    "MIDI output port could not be opened (count-in skipped).",
                                    f"Port: {midi_port}",
                                    str(e),
                                ],
                                title="Warning",
                            )

                            chain_selected_idx = play_chain(
                                chain,
                                bpm,
                                midi_port,
                                stdscr,
                                grid_win,
                                chain_win,
                                root,
                                use_color,
                                color_pairs,
                                chain_selected_idx,
                                _load,
                            )
                    else:

                        def _load(path):
                            return (
                                load_adt(path)
                                if path.lower().endswith(".adt")
                                else load_adp(path)
                            )

                        chain_selected_idx = play_chain(
                            chain,
                            bpm,
                            midi_port,
                            stdscr,
                            grid_win,
                            chain_win,
                            root,
                            use_color,
                            color_pairs,
                            chain_selected_idx,
                            _load,
                        )


                    
                    try:
                        if out_port is not None:
                            out_port.close()
                    except Exception:
                        pass

            mode = "VIEW"
            continue
        if ch in (ord("r"), ord("R")) and focus != "chain":
            repeat_mode = not repeat_mode
            continue

        if ch in (ord("c"), ord("C")):
            if (
                focus == "patterns"
                and list_mode == "patterns"
                and pattern_files
            ):
                old = pattern_files[selected_idx]
                new = toggle_p_b(old)
                if new:
                    oldp = os.path.join(root, old)
                    newp = os.path.join(root, new)
                    if not os.path.exists(newp):
                        try:
                            os.rename(oldp, newp)
                            pattern_files = scan_patterns(root)
                            if new in pattern_files:
                                selected_idx = pattern_files.index(new)
                            else:
                                selected_idx = 0

                            total_pf = len(pattern_files)
                            if inner > 0 and total_pf > 0:
                                visible_cap = inner * 2
                                if selected_idx < top_index:
                                    top_index = selected_idx
                                elif selected_idx >= top_index + visible_cap:
                                    top_index = max(
                                        0, selected_idx - visible_cap + 1
                                    )
                            load_preview()
                        except Exception as e:
                            msg = str(e)
                    else:
                        msg = "파일이 이미 존재"
            continue


def main():
    curses.wrapper(main_curses)


if __name__ == "__main__":
    main()
