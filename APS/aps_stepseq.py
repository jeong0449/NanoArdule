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
    bars: int = 2  # 2 bars = 32 steps


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

    # events -> grid (우리는 APS에서 grid로 변환해서 넘겨도 되지만, 여기서 다시 한번 만들어 씀)
    grid, non_grid = _build_stepgrid_from_events(drum_events, meta)

    modified = False
    saved = False


    cur_lane = 0
    cur_step = 0
    page = 0   # 0 = step 0–15, 1 = step 16–31

    max_y, max_x = stdscr.getmaxyx()

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
        page = 0 if cur_step < 16 else 1

    def draw():
        stdscr.erase()

        header = (
            "[STEP] {name}  CH={ch}  LEN={bars}bar  STEPS={steps}  BPM={bpm}  MOD={mod}"
            .format(
                name=meta.name,
                ch=meta.channel + 1,
                bars=meta.bars,
                steps=grid.steps,
                bpm=meta.bpm,
                mod="Y" if modified else "N",
            )
        )
        try:
            stdscr.addnstr(0, 0, header.ljust(max_x), max_x)
        except curses.error:
            pass

        start_step = page * 16
        end_step = start_step + 16
        y_step = 2
        col0 = 8

        try:
            stdscr.addnstr(y_step, 0, " " * max_x, max_x)
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

        row_start = y_step + 1
        for li, lane in enumerate(grid.lanes):
            y = row_start + li
            if y >= max_y - 2:
                break
            try:
                stdscr.addnstr(y, 0, lane.name.ljust(col0 - 1), col0 - 1)
            except curses.error:
                pass

            col = col0
            for s in range(start_step, end_step):
                cell = lane.cells[s]
                ch = "x" if cell.on else "."
                attr = curses.A_REVERSE if (li == cur_lane and s == cur_step) else 0
                try:
                    stdscr.addnstr(y, col, " " + ch, 2, attr)
                except curses.error:
                    pass
                col += 3

        footer = "Arrows:move  Enter:on/off  +/-:vel  [ ]:page  C:1→2bar  Space:play  W:save  Q/Esc:exit"
        try:
            stdscr.addnstr(max_y - 1, 0, footer.ljust(max_x), max_x)
        except curses.error:
            pass

        stdscr.refresh()

    def confirm_quit():
        msg_text = "Modified. Quit without saving? (y/N)"
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
            page = 0
            if cur_step >= 16:
                cur_step = 15
        elif key == ord("]"):
            page = 1
            if cur_step < 16:
                cur_step = 16

        elif key == ord("\n"):  # Space / Enter
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                cell.on = False
            else:
                cell.on = True
                if cell.vel <= 0:
                    cell.vel = 100
            modified = True

        elif key == ord("+"):
            cell = grid.lanes[cur_lane].cells[cur_step]
            if not cell.on:
                cell.on = True
                if cell.vel <= 0:
                    cell.vel = 100
            cell.vel = min(127, cell.vel + 8)
            modified = True

        elif key == ord("-"):
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                cell.vel = max(1, cell.vel - 8)
                modified = True

        elif key in (ord("c"), ord("C")):
            for lane in grid.lanes:
                for i in range(16):
                    src = lane.cells[i]
                    dst = lane.cells[i + 16]
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
            break

        elif key in (ord("q"), ord("Q"), 27):  # q / Q / ESC
            if modified and not saved:
                if not confirm_quit():
                    draw()
                    continue
            break

        clamp_cursor()
        draw()

    new_events = _apply_stepgrid_to_events(grid, meta, non_grid)
    return modified, saved, new_events
