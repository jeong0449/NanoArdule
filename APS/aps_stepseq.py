# ================================================================
# APS_STEPSEQ - Build/Version Stamp
# ------------------------------------------------
# BUILD_DATE_KST : 2025-12-17
# BUILD_TAG      : aps_stepseq-20251217
# CHANGE_NOTE    : StepSeq: cursor-only accent background, NC quit-without-saving dialog, legend inline text.
#
# Tip: If you are using git, also record the commit hash:
#   git rev-parse --short HEAD
# ================================================================

APS_STEPSEQ_BUILD_DATE_KST = "2025-12-17"
APS_STEPSEQ_BUILD_TAG = "aps_stepseq-20251217"
APS_STEPSEQ_CHANGE_NOTE = 'StepSeq: cursor-only accent background, NC quit-without-saving dialog, legend inline text.'

# aps_stepseq.py
# Step Sequencer module for APS (Ardule Pattern Studio)
#
# - 2 bar (32-step) drum step sequencer
# - Grid is 8 lanes (GM drum notes) x 32 steps
#
# APS 쪽에서 ADT 패턴의 grid를 DrumEvent 배열로 변환해 넘기고,
# 편집이 끝나면 다시 grid에 반영해서 사용합니다.

import curses
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Tuple



# NC-style dialog (defined in aps_ui.py)
try:
    from aps_ui import dialog_confirm
except Exception:
    dialog_confirm = None

# ----------------------------------------------------------------------
# Data structures
# ----------------------------------------------------------------------

@dataclass
class DrumEvent:
    """
    Simple drum event representation used inside Step Sequencer.
    APS must convert its internal pattern/grid to/from this structure.

    type: "on" or "off"
    """
    tick: int
    chan: int
    note: int
    vel: int
    type: str  # "on" or "off"


@dataclass
class StepCell:
    on: bool = False
    vel: int = 100


@dataclass
class StepLane:
    name: str
    note: int
    cells: List[StepCell] = field(default_factory=list)


@dataclass
class PatternMeta:
    """
    Minimal metadata needed for Step Sequencer.
    APS must fill these fields from ADT or pattern registry.
    """
    name: str
    bpm: int
    channel: int
    loop_len_ticks: int
    loop_start_tick: int = 0
    bars: int = 2  # 2 bars

    # Resolution hints (backward compatible defaults)
    steps: int = 32           # total steps in the loop (24/32/48)
    steps_per_bar: int = 16   # 12/16/24
@dataclass
class StepGrid:
    lanes: List[StepLane]
    steps: int = 32


# 기본 드럼 레인 정의 (GM 노트 번호)
DEFAULT_DRUM_LANES = [
    ("RIM", 37),
    ("HTOM", 48),
    ("MTOM", 45),
    ("LTOM", 41),
    ("OHH", 46),
    ("CHH", 42),
    ("SNARE", 38),
    ("KICK", 36),
]




# ----------------------------------------------------------------------
# Velocity/level mapping (ADT v2.2a)
# ----------------------------------------------------------------------

def level_to_vel(level: int) -> int:
    """Map ADT level (0..3) to representative MIDI velocity."""
    try:
        l = int(level)
    except Exception:
        l = 0
    if l <= 0:
        return 0
    if l == 1:
        return 48
    if l == 2:
        return 88
    return 120

def vel_to_level(vel: int) -> int:
    """Map MIDI velocity to ADT level (0..3)."""
    try:
        v = int(vel)
    except Exception:
        v = 0
    if v <= 0:
        return 0
    if v < 60:
        return 1
    if v < 110:
        return 2
    return 3

# ----------------------------------------------------------------------
# StepSeq inline velocity adjust (vim-style, non-cycling)
# - Keep existing j/k (lane move) intact; use Shift+J / Shift+K to adjust velocity.
# - Clamp within levels 1..3 (no cycling, no rest) to avoid creating "on + vel=0" cells.
# ----------------------------------------------------------------------

def _clamp_level_1_3(level: int) -> int:
    try:
        l = int(level)
    except Exception:
        l = 2
    if l < 1:
        return 1
    if l > 3:
        return 3
    return l

def _adjust_level_1_3(level: int, delta: int) -> int:
    return _clamp_level_1_3(_clamp_level_1_3(level) + int(delta))

# ----------------------------------------------------------------------
# Conversion helpers: (현재는 안 써도 되지만 남겨둠)
# ----------------------------------------------------------------------

def _build_stepgrid_from_events(
    drum_events: List[DrumEvent],
    meta: PatternMeta,
    drum_lanes=None,
    max_steps: int = 32,
) -> Tuple[StepGrid, List[DrumEvent]]:
    """
    DrumEvent 리스트를 StepGrid 구조로 투영.
    - CH == meta.channel 인 note_on 이벤트만 그리드에 반영
    - 그 외 이벤트(다른 채널, 다른 노트, off 등)는 non_grid_events로 반환
    """
    if drum_lanes is None:
        drum_lanes = DEFAULT_DRUM_LANES

    note_to_lane = {}
    lanes: List[StepLane] = []
    for name, note in drum_lanes:
        idx = len(lanes)
        note_to_lane[note] = idx
        lanes.append(
            StepLane(
                name=name,
                note=note,
                cells=[StepCell(on=False, vel=0) for _ in range(max_steps)],
            )
        )

    loop_len = meta.loop_len_ticks if meta.loop_len_ticks > 0 else 1
    step_ticks = float(loop_len) / float(max_steps)

    non_grid_events: List[DrumEvent] = []

    for ev in drum_events:
        if ev.type != "on":
            non_grid_events.append(ev)
            continue
        if ev.chan != meta.channel:
            non_grid_events.append(ev)
            continue

        lane_idx = note_to_lane.get(ev.note)
        if lane_idx is None:
            non_grid_events.append(ev)
            continue

        rel_tick = ev.tick - meta.loop_start_tick
        if rel_tick < 0:
            non_grid_events.append(ev)
            continue

        step_f = float(rel_tick) / step_ticks
        step_idx = int(round(step_f))
        if not (0 <= step_idx < max_steps):
            non_grid_events.append(ev)
            continue

        cell = lanes[lane_idx].cells[step_idx]
        if (not cell.on) or (ev.vel > cell.vel):
            cell.on = True
            cell.vel = ev.vel

    return StepGrid(lanes=lanes, steps=max_steps), non_grid_events


def _apply_stepgrid_to_events(
    grid: StepGrid,
    meta: PatternMeta,
    non_grid_events: List[DrumEvent],
    default_note_len_ratio: float = 1.0 / 16.0,
) -> List[DrumEvent]:
    """
    StepGrid를 다시 DrumEvent 리스트로 변환.
    - 각 on 셀에 대해 note_on + note_off 페어 생성
    - 길이는 loop_len_ticks * default_note_len_ratio
    """
    loop_len = meta.loop_len_ticks if meta.loop_len_ticks > 0 else 1
    steps = grid.steps
    step_ticks = float(loop_len) / float(steps)
    note_len_ticks = int(loop_len * default_note_len_ratio)

    new_events: List[DrumEvent] = []

    for lane in grid.lanes:
        for s in range(steps):
            cell = lane.cells[s]
            if not cell.on:
                continue

            on_tick = meta.loop_start_tick + int(round(float(s) * step_ticks))
            off_tick = on_tick + note_len_ticks

            new_events.append(
                DrumEvent(on_tick, meta.channel, lane.note, cell.vel, "on")
            )
            new_events.append(
                DrumEvent(off_tick, meta.channel, lane.note, 0, "off")
            )

    all_events = new_events + list(non_grid_events)
    all_events.sort(key=lambda e: e.tick)
    return all_events


# ----------------------------------------------------------------------
# Step Sequencer curses mode
# ----------------------------------------------------------------------

def stepseq_mode(
    stdscr,
    meta: PatternMeta,
    drum_events: List[DrumEvent],
    play_callback: Optional[Callable[[StepGrid, PatternMeta], None]] = None,
    drum_lanes=None,
) -> Tuple[bool, bool, List[DrumEvent]]:
    """
    Main entry point for APS.
    APS should call this from pattern-list view when the user presses 's'.

    return (modified, saved, new_drum_events)
    """
    curses.curs_set(0)

    # APS가 그려놓은 기존 화면을 완전히 지우기
    stdscr.clear()
    stdscr.refresh()


    # --- StepSeq local color pairs (avoid clobbering main UI) ---
    # NOTE: main screen should re-init its own pairs after StepSeq returns,
    # but we still keep StepSeq pairs in a high range to minimize collisions.
    has_colors = curses.has_colors()
    if has_colors:
        try:
            curses.start_color()
        except curses.error:
            has_colors = False

    # Cursor-only accent background (non-cursor cells stay plain white text)
    # Pair numbers chosen to be high and unlikely to collide with APS main.
    P_CURSOR_REST = 201  # '.' at cursor: white background
    P_CURSOR_L1   = 202  # '-' at cursor
    P_CURSOR_L2   = 203  # 'X' at cursor
    P_CURSOR_L3   = 204  # 'O' at cursor

    if has_colors:
        try:
            curses.init_pair(P_CURSOR_REST, curses.COLOR_BLACK, curses.COLOR_WHITE)
            curses.init_pair(P_CURSOR_L1,   curses.COLOR_BLACK, curses.COLOR_GREEN)
            curses.init_pair(P_CURSOR_L2,   curses.COLOR_BLACK, curses.COLOR_YELLOW)
            curses.init_pair(P_CURSOR_L3,   curses.COLOR_WHITE, curses.COLOR_RED)
        except curses.error:
            has_colors = False
    # events -> grid (우리는 APS에서 grid로 변환해서 넘겨도 되지만, 여기서 다시 한번 만들어 씀)
    # Use meta.steps if provided (24/32/48); keep fallback to 32
    max_steps = int(getattr(meta, "steps", 32) or 32)
    if max_steps not in (24, 32, 48):
        max_steps = 32

    # Derive steps_per_bar (2-bar patterns only) if missing
    spb = int(getattr(meta, "steps_per_bar", 0) or 0)
    if spb <= 0:
        spb = max_steps // 2  # 12 / 16 / 24

    # Normalize meta values
    meta.steps = max_steps
    meta.steps_per_bar = spb

    grid, non_grid = _build_stepgrid_from_events(drum_events, meta, drum_lanes=drum_lanes, max_steps=max_steps)

    modified = False
    saved = False


    cur_lane = 0
    cur_step = 0
    # One page = one bar (2-bar patterns only)
    page_size = int(getattr(meta, "steps_per_bar", 16) or 16)  # 12 / 16 / 24
    page = 0  # 0 = bar1, 1 = bar2

    # NOTE: max_y/max_x are queried inside draw() to stay stable across terminal resizes.

    # Dirty-state tracking: show '*' only when current grid differs from baseline (saved/original)
    def _grid_signature(g: StepGrid):
        # Compare only on/off and velocity level (0..3). Ignore raw MIDI velocities for stability.
        return tuple(
            (cell.on, vel_to_level(cell.vel) if cell.on else 0)
            for lane in g.lanes
            for cell in lane.cells
        )

    baseline_sig = _grid_signature(grid)

    def clamp_cursor():
        nonlocal cur_lane, cur_step, page
        if cur_lane < 0:
            cur_lane = 0
        if cur_lane >= len(grid.lanes):
            cur_lane = len(grid.lanes) - 1
        if cur_step < 0:
            cur_step = 0
        if cur_step >= grid.steps:
            cur_step = grid.steps - 1
        # 2-bar patterns: page is bar index (0 or 1)
        page = cur_step // page_size

    def draw():
        max_y, max_x = stdscr.getmaxyx()
        stdscr.erase()

        # Draw frame
        try:
            stdscr.border()
        except curses.error:
            pass

        header = (
            "[STEP] {name}  CH={ch}  LEN={bars}bar  STEPS={steps}  BPM={bpm}  MOD={mod}"
            .format(
                name=(meta.name + ('*' if modified else '')),
                ch=meta.channel + 1,
                bars=meta.bars,
                steps=grid.steps,
                bpm=meta.bpm,
                mod="Y" if modified else "N",
            )
        )
        try:
            stdscr.addnstr(1, 2, header.ljust(max_x - 4), max_x - 4)
        except curses.error:
            pass

        start_step = page * page_size
        end_step = min(start_step + page_size, grid.steps)
        y_step = 3
        col0 = 8

        try:
            stdscr.addnstr(y_step, 1, " " * (max_x - 2), max_x - 2)
        except curses.error:
            pass

        col = col0
        for s in range(start_step, end_step):
            label = "%02d" % (s + 1)
            try:
                stdscr.addnstr(y_step, col, label, 2)
            except curses.error:
                pass
            col += 3

        # Beat marker row (quarter-note based)
        beat_gap = 4
        if page_size == 12:
            beat_gap = 3
        elif page_size == 24:
            beat_gap = 6

        y_beat = y_step + 1
        try:
            stdscr.addnstr(y_beat, 1, " " * (max_x - 2), max_x - 2)
        except curses.error:
            pass

        col = col0
        local_idx = 0
        for _s in range(start_step, end_step):
            if col + 2 >= max_x - 1:
                break
            mark = "|" if (local_idx % beat_gap == 0) else " "
            try:
                stdscr.addnstr(y_beat, col, " " + mark, 2)
            except curses.error:
                pass
            col += 3
            local_idx += 1

        row_start = y_step + 2
        for li, lane in enumerate(grid.lanes):
            y = row_start + li
            if y >= max_y - 2:
                break
            try:
                stdscr.addnstr(y, 2, lane.name.ljust(col0 - 3), col0 - 3)
            except curses.error:
                pass

            col = col0
            for s in range(start_step, end_step):
                if col + 2 >= max_x - 1:
                    break
                cell = lane.cells[s]
                if cell.on:
                    lvl = vel_to_level(cell.vel)
                    # UI 표시용 문자(데이터에는 영향 없음): 평상시에도 대문자 표시
                    if lvl <= 0:
                        ch = "."
                    elif lvl == 1:
                        ch = "-"
                    elif lvl == 2:
                        ch = "X"
                    else:
                        ch = "O"
                else:
                    lvl = 0
                    ch = "."

                is_cursor = (li == cur_lane and s == cur_step)

                # 커서 위치에서만 배경색(액센트)을 보여줌. 그 외는 흰색 문자만.
                if is_cursor:
                    if has_colors:
                        if lvl <= 0:
                            attr = curses.color_pair(P_CURSOR_REST)
                        elif lvl == 1:
                            attr = curses.color_pair(P_CURSOR_L1)
                        elif lvl == 2:
                            attr = curses.color_pair(P_CURSOR_L2)
                        else:
                            attr = curses.color_pair(P_CURSOR_L3)
                    else:
                        attr = curses.A_REVERSE
                else:
                    attr = 0

                try:
                    stdscr.addnstr(y, col, " " + ch, 2, attr)
                except curses.error:
                    pass

                except curses.error:
                    pass
                col += 3

        # Velocity legend (symbol uses same accent background style; text stays normal)
        try:
            y_leg = max_y - 4
            x = 2
            stdscr.addnstr(y_leg, x, "Legend: ", max_x - x)
            x += len("Legend: ")

            def _draw_leg(sym: str, pair: int, label: str):
                nonlocal x
                # draw a 2-char "cell" like the grid: ' ' + sym with accent background
                if has_colors:
                    a = curses.color_pair(pair)
                else:
                    a = curses.A_REVERSE
                try:
                    stdscr.addnstr(y_leg, x, " " + sym, 2, a)
                except curses.error:
                    return
                x += 2
                # a single space, then label
                try:
                    stdscr.addnstr(y_leg, x, " " + label + "  ", max_x - x)
                except curses.error:
                    return
                x += len(" " + label + "  ")

            _draw_leg(".", P_CURSOR_REST, "REST")
            _draw_leg("-", P_CURSOR_L1, "SOFT")
            _draw_leg("X", P_CURSOR_L2, "MEDIUM")
            _draw_leg("O", P_CURSOR_L3, "STRONG")
        except curses.error:
            pass

        except curses.error:
            pass

        footer = "Move: arrows/h/j/k/l  Enter:toggle  J/K:vel  [ ]:bar  c:copy bar1->bar2  Space:play  w:save  q/Esc:exit"
        try:
            stdscr.addnstr(max_y - 2, 1, footer.ljust(max_x - 2), max_x - 2)
        except curses.error:
            pass

        stdscr.refresh()

    def confirm_quit():
        """Confirm quitting StepSeq when there are unsaved changes.

        Uses NC-style dialog from aps_ui.py if available; otherwise falls back to a simple prompt.
        """
        # Preferred: NC-style dialog (no title, no shadow, boxed)
        if callable(dialog_confirm):
            try:
                return bool(dialog_confirm(
                    stdscr,
                    "Modified. Quit without saving?",
                    yes_label="YES",
                    no_label="NO",
                    default_yes=False,
                ))
            except Exception:
                # fall through to legacy prompt
                pass

        # Fallback: legacy inline prompt (centered)
        msg_text = "Modified. Quit without saving? (y/N)"
        max_y, max_x = stdscr.getmaxyx()
        y = max_y // 2
        x = max(0, (max_x - len(msg_text)) // 2)
        try:
            stdscr.addnstr(y, x, msg_text, len(msg_text), curses.A_REVERSE)
        except curses.error:
            pass
        stdscr.refresh()
        while True:
            k = stdscr.getch()
            if k in (ord("y"), ord("Y")):
                return True
            if k in (ord("n"), ord("N"), 27, ord("\n")):
                return False


    clamp_cursor()
    draw()

    while True:
        key = stdscr.getch()
        if key == curses.KEY_RESIZE:
            draw()
            continue

        if key in (curses.KEY_UP, ord("k")):
            cur_lane -= 1
        elif key in (curses.KEY_DOWN, ord("j")):
            cur_lane += 1
        elif key in (curses.KEY_LEFT, ord("h")):
            cur_step = (cur_step - 1) % grid.steps
        elif key in (curses.KEY_RIGHT, ord("l")):
            cur_step = (cur_step + 1) % grid.steps
        elif key == ord("\t"):
            cur_lane = (cur_lane + 1) % len(grid.lanes)

        elif key == ord("["):
            # previous page
            if page > 0:
                page -= 1
            start = page * page_size
            end = min(start + page_size, grid.steps) - 1
            if cur_step < start:
                cur_step = start
            if cur_step > end:
                cur_step = end
        elif key == ord("]"):
            # next page
            max_page = (grid.steps - 1) // page_size
            if page < max_page:
                page += 1
            start = page * page_size
            end = min(start + page_size, grid.steps) - 1
            if cur_step < start:
                cur_step = start
            if cur_step > end:
                cur_step = end

        elif key == ord("\n"):  # Space / Enter
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                cell.on = False
            else:
                cell.on = True
                if cell.vel <= 0:
                    cell.vel = 88
            modified = True
        elif key == ord('K'):  # Shift+K: stronger (vim-style, non-cycling)
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                lvl = vel_to_level(cell.vel)
                if lvl < 1:
                    lvl = 2
                lvl = _adjust_level_1_3(lvl, +1)
                cell.vel = level_to_vel(lvl)
                modified = True

        elif key == ord('J'):  # Shift+J: weaker (vim-style, non-cycling)
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                lvl = vel_to_level(cell.vel)
                if lvl < 1:
                    lvl = 2
                lvl = _adjust_level_1_3(lvl, -1)
                cell.vel = level_to_vel(lvl)
                modified = True
        elif key in (curses.KEY_PPAGE, 339):  # PgUp: stronger
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                lvl = vel_to_level(cell.vel)
                if lvl < 1:
                    lvl = 2
                elif lvl < 3:
                    lvl += 1
                cell.vel = level_to_vel(lvl)
                modified = True

        elif key in (curses.KEY_NPAGE, 338):  # PgDn: weaker (but not rest)
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                lvl = vel_to_level(cell.vel)
                if lvl > 1:
                    lvl -= 1
                else:
                    lvl = 1
                cell.vel = level_to_vel(lvl)
                modified = True
        elif key in (ord("c"), ord("C")):
            # Copy bar1 -> bar2 (page_size steps) when bar2 exists
            if grid.steps >= 2 * page_size:
                for lane in grid.lanes:
                    for i in range(page_size):
                        src = lane.cells[i]
                        dst = lane.cells[i + page_size]
                        dst.on = src.on
                        dst.vel = src.vel
                modified = True

        # Space: 현재 그리드를 한 번 재생
        elif key == 32:  # Space
            if play_callback:
                # 1) 재생 실행
                play_callback(grid, meta)

                # 2) 재생 동안 쌓인 키(특히 Space)를 모두 버리기
                try:
                    stdscr.nodelay(True)
                    while True:
                        k2 = stdscr.getch()
                        if k2 == -1:
                            break
                    stdscr.nodelay(False)
                except curses.error:
                    stdscr.nodelay(False)


        elif key in (ord("w"), ord("W")):
            saved = True
            baseline_sig = _grid_signature(grid)
            modified = False
            break

        elif key in (ord("q"), ord("Q"), 27):  # q / Q / ESC
            if modified and not saved:
                if not confirm_quit():
                    draw()
                    continue
            break

        clamp_cursor()
        modified = (_grid_signature(grid) != baseline_sig)
        draw()

    # --- Restore curses state for APS main ---
    try:
        curses.curs_set(0)
    except curses.error:
        pass

    try:
        stdscr.keypad(True)
        curses.noecho()
        curses.cbreak()
        stdscr.clear()
        stdscr.refresh()
    except curses.error:
        pass

    new_events = _apply_stepgrid_to_events(grid, meta, non_grid)
    return modified, saved, new_events
