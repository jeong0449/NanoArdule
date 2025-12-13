# aps_ui.py — curses UI helpers for APS v0.27+
import curses
from typing import List, Optional, Tuple

from aps_core import Pattern, ChainEntry, compute_timing, describe_timing, HIT_CHAR
from aps_sections import ChainSelection, SectionManager
from aps_countin import get_countin_presets   # (헬프, Count-in 메뉴 안내용)


def draw_grid(pattern: Optional[Pattern], win, current_step, use_color, color_pairs):
    """
    패턴 그리드 프리뷰.
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

    # --- 레이아웃 설정 ---
    label_w = 4  # 왼쪽 KK/SN 같은 약자 자리
    inner_w = w - 2

    # 오른쪽 악기 설명 텍스트 ("KK: KICK" 형식)
    instr_texts = [
        f"{abbr}: {name}"
        for abbr, name in zip(pattern.slot_abbr, pattern.slot_name)
    ]
    if instr_texts:
        max_instr_len = max(len(t) for t in instr_texts)
    else:
        max_instr_len = 0
    instr_w = min(max_instr_len + 1, max(10, inner_w // 3))  # 최소 10, 최대 1/3 정도

    # 그리드가 쓸 수 있는 최대 x 좌표
    grid_max_x = w - 1 - instr_w - 1  # 오른쪽 테두리 - 악기컬럼 - 1칸 여유
    if grid_max_x <= label_w + 1:
        # 너무 좁으면 악기 컬럼 포기하고 그리드만
        grid_max_x = w - 2
        instr_w = 0

    # 타이밍 정보
    beats, bars, spb, spbar = compute_timing(pattern)

    # KK가 아래로 오도록 slot을 뒤집어서 사용
    slots = list(range(pattern.slots - 1, -1, -1))

    # --- 그리드 + 오른쪽 악기 설명 ---
    for row_idx, s in enumerate(slots):
        y = 1 + row_idx
        # 맨 아래 한 줄은 legend 용으로 남겨둠
        if y >= h - 2:
            break

        # 슬롯 라벨 (약자)
        label = pattern.slot_abbr[s]
        try:
            win.addstr(y, 1, f"{label:>3} ")
        except curses.error:
            pass

        grid_start_x = 1 + label_w

        # step → visual_step(=bar 사이에 공백 1칸 삽입) 변환
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
                # 현재 재생 스텝: 색은 play, no-hit면 '|'로 표시
                ch = HIT_CHAR if acc > 0 else "|"
                if use_color:
                    try:
                        attr |= curses.color_pair(color_pairs["play"])
                    except Exception:
                        pass
            else:
                if acc == 0:
                    # no-hit 점: beat 단위로 색 번갈아
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
                    # 악센트 히트
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

        # 오른쪽 악기 설명 컬럼 (KK: KICK)
        if instr_w > 0:
            instr_x = grid_max_x + 1  # 그리드 끝 + 1칸
            text = f"{pattern.slot_abbr[s]}: {pattern.slot_name[s]}"
            try:
                win.addstr(y, instr_x, text[:instr_w].ljust(instr_w))
            except curses.error:
                pass

    # --- 아래쪽 한 줄: no-hit + 액센트 legend ---
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

    # even-beat no-hit (white)
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

    # odd-beat no-hit (cyan)
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
    focus_chain: bool,
    selected_idx: int,
    selection: ChainSelection,
    section_mgr: SectionManager,
    countin_label: str,
):
    """
    체인 뷰:
    - sel_range: 블록 선택 영역(항상 반전)
    - selected_idx: 현재 삽입 위치(포커스가 없어도 항상 표시)
    - 포커스 창은 제목 앞에 ▶ 표시, 선택 줄은 역상+굵게
    - 비포커스 창은 제목에 공백, 선택 줄은 노란색 굵게
    - countin_label: 현재 선택된 Count-in 상태 (예: None, SimpleHH...)
    """
    win.erase()
    h, w = win.getmaxyx()
    win.box()

    ci = countin_label or "None"
    if focus_chain:
        title = f" ▶ Pattern Chain — APS v0.27+ [CI:{ci}] "
    else:
        title = f"   Pattern Chain — APS v0.27+ [CI:{ci}] "

    try:
        win.addstr(0, 2, title[:w - 4])
    except curses.error:
        pass

    if not chain:
        try:
            win.addstr(1, 2, "체인이 비어 있습니다.")
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
            # 블록 선택: 항상 반전
            try:
                win.addstr(y, 1, line[:w - 2].ljust(w - 2), curses.A_REVERSE)
            except curses.error:
                pass
        elif row == selected_idx:
            # 현재 하이라이트 위치: 포커스 여부와 상관없이 항상 표시
            if focus_chain:
                # 체인 창에 포커스: 역상 + 굵게
                attr = curses.A_REVERSE | curses.A_BOLD
            else:
                # 비포커스: 노란색 굵게 (색 없으면 그냥 굵게)
                attr = curses.A_BOLD
                try:
                    attr |= curses.color_pair(10)  # 10번 페어: 노랑 (main에서 초기화)
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
    상단 메뉴바 표시.
    F-key 매핑 (v0.27 최신):

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
    """
    패턴 정보 + 슬롯 약자/이름/노트 번호 + 그리드 색상 legend(영문 설명) 표시.
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
        ab = p.slot_abbr[i]
        nm = p.slot_name[i]
        nt = p.slot_note[i]
        lines.append(f"  {i:02d}: {ab}  ->  {nm} (note {nt})")

    # 그리드 색상/악센트 설명 (영문)
    lines.extend(
        [
            "",
            "Grid color legend:",
            "  · (white)  : no hit on even beats",
            "  · (cyan)   : no hit on odd beats",
            "  x (green)  : soft accent (acc1)",
            "  x (yellow) : medium accent (acc2)",
            "  x (red)    : strong accent (acc3)",
            "  x (blue)   : current playing step",
        ]
    )

    lines.append("")
    lines.append("Press any key...")

    max_y, max_x = stdscr.getmaxyx()
    h = min(len(lines) + 2, max_y - 2)
    w = min(max(len(s) for s in lines) + 4, max_x - 2)
    y = (max_y - h) // 2
    x = (max_x - w) // 2
    win = curses.newwin(h, w, y, x)
    win.box()
    visible_lines = lines[: h - 2]
    for i, s in enumerate(visible_lines):
        try:
            win.addstr(1 + i, 2, s[: w - 4])
        except curses.error:
            pass
    win.refresh()
    win.getch()


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
            # Prompt + 현재 입력 내용
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


# ======== 섹션 오버뷰 / 블록/섹션 선택 / 붙여넣기 위치 선택 / Count-in 선택 / 헬프 ========

def show_section_overview_curses(
    stdscr, chain: List[ChainEntry], section_mgr: SectionManager, current_idx: int
):
    """
    SectionManager에 등록된 섹션들을 한눈에 보여주는 창.
    (섹션 이름 + row 범위 + 길이)
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
    붙여넣기 시 호출: 현재 클립보드와 정의된 섹션들 중에서
    어떤 블록을 붙여넣을지 선택.
    반환값: (entries_to_paste, label) 또는 None
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
    붙여넣기 후, 선택된 블록을 현재 라인의 '위' 또는 '아래'에 붙일지 선택.
    반환값: "before" / "after" / None
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
    F3: Count-in preset 선택 창.
    - 첫 줄은 (None)
    - 이후는 aps_countin.py 안에 정의된 내장 패턴 이름들
    반환값: -1 = None, 0..N-1 = 선택된 preset index, None = 취소
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

        # 맨 아랫줄: 이 데이터가 어느 스크립트 파일에 있는지 표시
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
            # 선택 확정
            if idx == 0:
                return -1   # None
            else:
                return idx - 1
        elif ch in (27, ord("q")):
            # 취소
            return None


def show_help_curses(stdscr):
    """
    편집용 키 요약을 보여주는 헬프 창 (F1).
    """
    lines = [
        "APS Chain Editor Keys",
        "",
        "[Focus]",
        "  Tab              : switch focus (Patterns/ARR <-> Chain)",
        "",
        "[Left list (Patterns / ARR)]",
        "  F4               : toggle left list (Patterns <-> ARR) & refresh from disk",
        "",
        "  (Patterns mode)",
        "    Arrow / hjkl   : move selection",
        "    Enter          : add pattern after cursor (merges xN when same)",
        "    O              : add pattern before cursor (merges xN when same)",
        "    c              : toggle _P### <-> _B### of selected pattern file",
        "",
        "  (ARR mode)",
        "    Arrow / hjkl   : move selection",
        "    Enter          : expand selected ARR into chain (as plain steps)",
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
        "  r              : toggle repeat (pattern playback only)",
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
