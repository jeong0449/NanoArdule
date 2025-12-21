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
    compute_timing,  # (현재 직접 쓰진 않지만 남겨둠)
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
from aps_countin import get_countin_presets  # 내장 카운트-인 패턴들 (이름/메타 용)

try:
    import mido
except ImportError:
    mido = None

import aps_stepseq

# Used by show_warning_popup wrapper to call NC-style dialogs without threading stdscr everywhere.
_GLOBAL_STDSCR_FOR_DIALOGS = None

def toggle_p_b(fname: str) -> Optional[str]:
    """
    파일명 끝의 _P### / _B### 를 서로 토글.
    예: SWG_P001.ADT -> SWG_B001.ADT
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
    MIDI 출력 포트 자동 선택:

    1) 이름에 'microsoft' 가 들어있지 않은 포트를 우선
    2) 모두 Microsoft 계열이면 첫 번째 포트
    3) 포트가 없으면 None
    """
    if mido is None:
        return None

    try:
        names = mido.get_output_names()
    except Exception:
        return None

    if not names:
        return None

    # 'microsoft' 가 이름에 포함되지 않은 포트 우선 (대소문자 무시)
    non_ms = [n for n in names if "microsoft" not in n.lower()]
    if non_ms:
        return non_ms[0]

    # 모두 Microsoft 계열이면 첫 번째 포트 사용
    return names[0]


def main_curses(stdscr):
    curses.curs_set(0)
    stdscr.keypad(True)
    global _GLOBAL_STDSCR_FOR_DIALOGS
    _GLOBAL_STDSCR_FOR_DIALOGS = stdscr


    use_color = False    # 색상 사용 여부
    color_pairs = {}
    highlight_unfocused_pair = 0  # 비포커스 하이라이트용 컬러 페어 번호

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


    # 패턴 루트 디렉터리:
    #   - ./patterns 폴더가 있으면 그쪽을 우선 사용
    #   - 없으면 현재 디렉터리(".") 사용
    if os.path.isdir("patterns"):
        root = "patterns"
    else:
        root = "."

    # 패턴 / ARR 리스트
    pattern_files: List[str] = scan_patterns(root)
    arr_files: List[str] = sorted(
        f for f in os.listdir(root) if f.lower().endswith(".arr")
    )

    # 왼쪽 리스트 모드: "patterns" / "arr"
    list_mode: str = "patterns"

    selected_idx = 0
    loaded_pattern: Optional[Pattern] = None
    chain: List[ChainEntry] = []
    chain_selected_idx = 0  # 체인 커서 (삽입 기준)
    focus = "patterns"  # "patterns" 또는 "chain"
    bpm = 120
    repeat_mode = False
    msg = ""
    mode = "VIEW"
    selection = ChainSelection()
    section_mgr = SectionManager()

    # --- Undo stack: (chain, chain_selected_idx, selection, section_mgr, bpm) ---
    undo_stack: List[
        tuple[List[ChainEntry], int, ChainSelection, SectionManager, int]
    ] = []

    # --- Clipboard (cut/copy한 블록) ---
    clipboard: List[ChainEntry] = []

    # --- Count-in 상태 ---
    countin_idx: int = -1  # -1 = 없음, 0..N-1 = get_countin_presets() 인덱스
    countin_presets: List[Pattern] = get_countin_presets()

    # --- Hybrid / Composite 상태 (A/B 소스, 합성 프리뷰, HYB_P9xx.APT 자동 번호) ---
    bar_sources: List[int] = []          # A/B 소스로 선택된 패턴 인덱스들 (최대 2개)
    composite_mode: bool = False         # True면 합성 프리뷰 모드
    composite_swap: bool = False         # False: A1+B2, True: A2+B1
    composite_pattern: Optional[Pattern] = None  # 현재 합성된 패턴
    hyb_next_index: int = 901            # HYB_P9xx.APT 자동 증가 인덱스

    # --- 왼쪽 리스트의 "첫 번째로 보이는 인덱스" (페이지 스크롤용) ---
    top_index = 0

    def get_countin_label() -> str:
        if countin_idx < 0:
            return "None"
        if 0 <= countin_idx < len(countin_presets):
            return countin_presets[countin_idx].name
        return "?"

    def push_undo():
        # 깊은 복사로 현재 상태를 스택에 저장
        snapshot = (
            copy.deepcopy(chain),
            chain_selected_idx,
            copy.deepcopy(selection),
            copy.deepcopy(section_mgr),
            bpm,
        )
        undo_stack.append(snapshot)
        # 너무 오래된 것은 버리기 (최근 100단계만 유지)
        if len(undo_stack) > 100:
            undo_stack.pop(0)

    def load_preview():
        """현재 pattern_files / selected_idx 기반으로 프리뷰 로드 (list_mode=patterns일 때만 의미 있음)."""
        nonlocal loaded_pattern, msg
        if list_mode != "patterns":
            # ARR 모드에서는 프리뷰 없음
            loaded_pattern = None
            return
        if not pattern_files:
            loaded_pattern = None
            return
        if selected_idx < 0 or selected_idx >= len(pattern_files):
            loaded_pattern = None
            return
        # 합성 프리뷰 모드에서는 composite_pattern을 그대로 사용
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

        default_name = f"HYB_P{hyb_next_index:03d}.APT"
        t = prompt_text(stdscr, f"Save hybrid pattern [{default_name}]:")
        if t is None:
            msg = "Save canceled."
            return
        if not t:
            t = default_name
        # 확장자 없으면 .APT 붙이기
        if "." not in t:
            t += ".APT"

        path = os.path.join(root, t)

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
                import json as _json  # 로컬 import (aps_core의 json과 동일)
                _json.dump(data, f, ensure_ascii=False, indent=2)

            msg = f"Saved hybrid pattern: {t}"
            hyb_next_index += 1

            # 저장 후 패턴 목록 다시 스캔 (새 HYB_P9xx.APT를 보이게)
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
        """ARR 파일에서 #COUNTIN 헤더를 읽어 countin_idx를 복원."""
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
                            # 프리셋 이름과 매칭
                            idx = -1
                            for i, p in enumerate(countin_presets):
                                if p.name == name:
                                    idx = i
                                    break
                            countin_idx = idx
                        break
        except Exception:
            # 없거나 읽기 실패하면 그냥 무시
            pass

    def choose_arr_file_curses(stdscr, arrs: List[str]) -> Optional[str]:
        """
        ARR 파일 목록에서 하나를 선택하는 작은 팝업.
        (현재 F-키에서는 사용하지 않지만, 남겨둠)
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
        현재 패턴 리스트에서 선택된 .ADT 패턴(2 bar, 32 step)을
        스텝 시퀀서에 넘겨서 편집하고, 결과를 메모리상의 pat.grid에 반영한다.
        P 키를 누르면 현재 StepGrid를 MIDI로 재생한다.
        """
        nonlocal loaded_pattern, msg, selected_idx, pattern_files, bpm, midi_port

        # 1) 이 함수는 패턴 리스트 포커스에서만 동작
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

        # 2) ADT 로드
        path = os.path.join(root, fname)
        try:
            pat = load_adt(path)
        except Exception as e:
            msg = f"ADT load error: {e}"
            return

        # 3) 2 bar (32 step) 패턴만 지원
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

# 7) P 키에서 호출될 재생 콜백 정의
        def play_stepseq(grid, meta_inner):
            """
            StepSeq 내부에서 Space 키를 눌렀을 때 호출되는 콜백.
            현재 StepGrid를 MIDI로 한 번 재생하고,
            재생 중에는 현재 재생 중인 bar 번호(1 또는 2)를 화면 아래에 표시한다.
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
                # StepGrid -> DrumEvent 리스트 (non_grid 이벤트는 없음)
                events = aps_stepseq._apply_stepgrid_to_events(
                    grid,
                    meta_inner,
                    [],  # non_grid_events 없음
                )

                # tick → 시간 변환
                ticks_per_quarter = 480.0
                sec_per_quarter = 60.0 / float(meta_inner.bpm)
                sec_per_tick = sec_per_quarter / ticks_per_quarter

                import time as _time

                # 2-bar 기준으로 bar 경계 계산
                loop_len = meta_inner.loop_len_ticks
                half_loop = loop_len // 2 if loop_len > 0 else 1

                def show_bar_label(bar_no: int):
                    # 그리드 아래쪽에 크게 표시
                    max_y, max_x = stdscr.getmaxyx()
                    text = f" PLAYING BAR {bar_no} "
                    y = max_y - 3  # footer 바로 위 줄 정도
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
                        # tick 기반으로 현재 bar 계산 (1 또는 2)
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
                            # 개별 이벤트 실패는 무시
                            pass

                # 재생이 끝나면 표시 지우기
                clear_bar_label()

            except Exception:
                # 재생 중 오류는 편집세션을 죽이지 않도록 무시
                pass


        # 8) 스텝 시퀀서 진입 (이제 P 키가 play_stepseq를 호출함)
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

        # 9) 변경 사항도 없고 저장도 안 하면 그대로 종료
        if (not modified) and (not saved):
            msg = "StepSeq: 변경 없음"
            return
        # 10) pat.grid에서 드럼 슬롯들만 모두 0으로 초기화
        for step in range(steps):
            row = pat.grid[step]
            for slot_idx in note_to_slot.values():
                if 0 <= slot_idx < len(row):
                    row[slot_idx] = 0

        # 11) 새 DrumEvent를 grid에 다시 반영 (note_on만 사용)
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

        # 12) 수정된 패턴을 프리뷰로 사용
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
        # 안전 가드: midi_port가 아직 로컬에 없으면 기본값을 자동 선택
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

        # 현재 왼쪽 리스트(패턴 / ARR) 결정
        current_list = arr_files if list_mode == "arr" else pattern_files

        # Pattern / ARR list window
        list_win = stdscr.derwin(work_height, list_w, work_top, 0)
        list_win.box()

        # 포커스 + 모드에 따라 제목 표현
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
        inner = list_h - 2                 # 한 화면에 보이는 "행" 수
        col_w = (list_w2 - 2) // 2
        total = len(current_list)

        # top_index가 너무 뒤로 밀려 있으면 보정
        if total > 0:
            max_top = max(0, total - 1)
            if top_index > max_top:
                top_index = max_top
            if top_index < 0:
                top_index = 0
        else:
            top_index = 0

        # --- 2열 리스트 렌더링 ---
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
        # 합성 프리뷰일 때 A/B 패턴명 및 모드 표시
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

                # 너무 오른쪽으로 밀리지 않도록 ‘표시 상한’을 둔다
                # grid 내용은 보통 왼쪽 0~약 gw*0.75까지 사용 → 나머지 25% 공간만 사용
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
        
        

        # --- 헬퍼: 선택된 인덱스가 화면에 보이도록 스크롤 조정 ---
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

        # --- 헬퍼: 여러 줄 텍스트를 중앙 팝업(반전)으로 보여주기 ---
        def show_text_popup(lines_to_show: List[str], title: str = "Info"):
            nonlocal stdscr
            max_y, max_x = stdscr.getmaxyx()
            # 여백 포함한 폭/높이 계산
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
                # 표시 가능한 줄 수
                cap = h - 4
                for i, ln in enumerate(content[:cap]):
                    win.addnstr(2 + i, 2, ln.ljust(w - 4), w - 4, curses.A_REVERSE)
                hint = "Press any key to dismiss"
                if len(hint) < w - 4:
                    win.addnstr(h - 2, w - len(hint) - 2, hint, len(hint), curses.A_REVERSE)
                win.refresh()
                win.getch()
            except curses.error:
                # fallback: 상태 메시지로
                show_message(stdscr, f"{title}: " + (content[0] if content else ""), 2.0)

        # --- F5: 선택 패턴을 9xx 번호로 즉시 복제 ---

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
            # 901부터 빈 슬롯 탐색
            for n in range(901, 999):
                dst_base = f"{genre}_P{n:03d}"
                dst_name = dst_base + ext
                dst_path = os.path.join(root, dst_name)
                if not os.path.exists(dst_path):
                    # 파일 복사(바이너리)
                    try:
                        with open(os.path.join(root, src_name), "rb") as fsrc:
                            data = fsrc.read()
                        with open(dst_path, "wb") as fdst:
                            fdst.write(data)
                        # 리스트 갱신 및 새 파일 선택
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

        # F2: Pat/ARR 리스트 토글 + 리프레시
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

        # F3: Refresh (현재 모드 유지, 디렉터리 재스캔)
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
                    if rep > 1:
                        seq_tokens.append(f"{idx}x{rep}")
                    else:
                        seq_tokens.append(str(idx))

                # Derive #PLAY (informational; sections + bare patterns)
                play_lines: List[str] = []
                last_sec = None
                for e in chain:
                    sec = getattr(e, "section", None)
                    if sec:
                        if sec != last_sec:
                            play_lines.append(sec)
                            last_sec = sec
                    else:
                        idx = pool_map.get(getattr(e, "filename", ""), None)
                        rep = int(getattr(e, "repeats", 1) or 1)
                        if idx is not None:
                            if rep > 1:
                                play_lines.append(f"@{idx}x{rep}")
                            else:
                                play_lines.append(f"@{idx}")
                        last_sec = None

                out_lines: List[str] = []
                out_lines.extend(header_lines)
                out_lines.extend(section_lines)
                out_lines.append("# APS ARR v1")
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

        # F5: DupPat (선택 패턴을 9xx로 즉시 복제)
        if ch == curses.KEY_F5:
            duplicate_selected_pattern()
            continue

            if loaded_pattern:
                show_pattern_info_curses(stdscr, loaded_pattern)
            continue

        # F6: MIDI 포트 선택
        if ch == curses.KEY_F6:
            name = choose_midi_port_curses(stdscr)
            if name:
                midi_port = name
            continue

        # F7: 저장
        # - 합성 모드(composite_mode=True)면 HYB_P9xx.APT로 패턴 저장
        # - 그 외에는 기존처럼 ARR 저장
        if ch in (curses.KEY_F7, ord('w'), ord('W')):
            if composite_mode and composite_pattern is not None:
                save_composite_pattern()
                continue

            # ARR 저장: ADP가 섞여 있으면 ARR에는 .ADT로 바꿔서 저장 + 메시지
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
                
            base = dialog_input(stdscr, "ARR filename:", default_text="", maxlen=64, suffix=".ARR")
            if base is None:
                msg = "Save canceled."
                continue

            if not base:
                msg = "Filename is empty."
                continue

            arr_filename = base + ".ARR"

            path = os.path.join(root, arr_filename)
            try:
                # ADP → ADT 변환을 반영한 복사본을 만들어 저장
                chain_for_save = [
                    ChainEntry(e.filename, e.repeats) for e in chain
                ]
                had_adp = False
                for e in chain_for_save:
                    if e.filename.lower().endswith(".adp"):
                        had_adp = True
                        base, _ext = os.path.splitext(e.filename)
                        e.filename = base + ".ADT"

                # 1차로 기본 ARR를 저장
                save_arr(path, chain_for_save, bpm)

                # 그 뒤에 #COUNTIN 헤더를 삽입하여 카운트-인 상태 기록
                try:
                    old_lines: List[str] = []
                    with open(
                        path, "r", encoding="utf-8", errors="ignore"
                    ) as f:
                        for line in f:
                            if line.startswith("#COUNTIN") or line.startswith("#SECTION"):
                                continue
                            old_lines.append(line.rstrip("\n"))

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

                    with open(path, "w", encoding="utf-8") as f:
                        f.write(header + "\n")
                        for sec, s2, e2 in section_blocks:
                            f.write(f"#SECTION {sec} {s2} {e2}\n")
                        for ln in old_lines:
                            f.write(ln + "\n")

                except Exception:
                    # 헤더 추가 실패해도 기본 ARR는 살아 있으므로 조용히 무시
                    pass

                if had_adp:
                    msg = f"Saved {t} (ADP → ADT in ARR)"
                else:
                    msg = f"Saved {t}"
            except Exception as e:
                msg = str(e)
            continue

        # F8: Count-in 선택
        if ch == curses.KEY_F8:
            new_idx = choose_countin_curses(stdscr, countin_idx)
            if new_idx is not None:
                countin_idx = new_idx  # -1 = None, 0..N-1 = preset
            continue

        # F9: BPM 변경
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

        # 포커스 토글 (Tab)
        if ch == ord("\t"):
            focus = "chain" if focus == "patterns" else "patterns"
            continue

        # 체인 포커스: 이동/반복/삭제/섹션 정의 등 (블록 편집 포함)
        if focus == "chain":
            # ESC: 블록 선택 해제
            if ch == 27:  # ESC
                if selection.get_range():
                    selection.reset()
                    msg = "Selection cleared"
                continue

            # 체인 창에 포커스가 있을 때는 Enter로 패턴을 삽입하지 않는다.
            if ch in (10, 13):  # Enter
                continue

            rng = selection.get_range()

            # 1) Delete 키: 블록 삭제 (선택 범위 전체 삭제)
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

            # 2) x / X: 블록 잘라내기 (Cut)
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

            # 3) y / Y: 블록 복사 (Copy)
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
                continue

            # 4) p / P: 붙여넣기 (클립보드/섹션 중 선택 후, 위/아래 위치 선택)
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
                section_mgr.shift_after_insert(
                    insert_at, len(entries_to_paste)
                )
                chain_selected_idx = insert_at
                selection.reset()
                msg = f"Pasted {len(entries_to_paste)} step(s) from {label}"
                continue

            # 체인 키 기본 처리 (이동, 한 줄 단위 삭제/반복, O/o 등)
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

        # Pattern list focus: 패턴/ARR 선택 이동
        if focus == "patterns":
            current_list = arr_files if list_mode == "arr" else pattern_files
            total = len(current_list)

            # ↑ / k : 한 항목 위로
            if ch in (curses.KEY_UP, ord("k")):
                if total > 0 and selected_idx > 0:
                    selected_idx -= 1
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # ↓ / j : 한 항목 아래로
            if ch in (curses.KEY_DOWN, ord("j")):
                if total > 0 and selected_idx < total - 1:
                    selected_idx += 1
                    ensure_visible(total)
                    if list_mode == "patterns":
                        load_preview()
                continue

            # ← / h : 오른쪽 컬럼 → 왼쪽 컬럼
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

            # → / l : 왼쪽 컬럼 → 오른쪽 컬럼
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

            # 's' / 'S' : Step Sequencer 진입
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

            # ESC : 합성 프리뷰/선택 해제
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

        # ===== 공통 동작 =====

        # Enter: 체인에 삽입
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
                                section_mgr.shift_after_insert(insert_at, 1)
                                chain_selected_idx = insert_at
            else:
                if arr_files:
                    arr_name = arr_files[selected_idx]
                    arr_path = os.path.join(root, arr_name)
                    try:
                        load_countin_from_arr(arr_path)
                        parsed = parse_arr(arr_path)
                        if isinstance(parsed, tuple) and len(parsed) >= 2:
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
                            else:
                                if (
                                    chain_selected_idx < 0
                                    or chain_selected_idx >= len(chain)
                                ):
                                    chain_selected_idx = len(chain) - 1
                                insert_at = chain_selected_idx + 1
                                for i, e in enumerate(block):
                                    chain.insert(insert_at + i, e)
                                section_mgr.shift_after_insert(
                                    insert_at, len(block)
                                )
                                chain_selected_idx = insert_at
                            msg = f"Inserted ARR '{arr_name}' ({len(block)} steps)"
                    except Exception as e:
                        msg = f"ARR insert error: {e}"
            continue

        # Shift+O
        if ch == ord("O") and list_mode == "patterns":
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
                            section_mgr.shift_after_insert(insert_at, 1)
                            chain_selected_idx = insert_at
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

        if ch in (ord("r"), ord("R")):
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