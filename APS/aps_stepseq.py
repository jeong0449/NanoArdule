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
import textwrap
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Tuple
import os
import time
import heapq

# Optional dependency (for StepSeq live pad input)
try:
    import mido
except Exception:
    mido = None




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
# MIDI live input helpers (StepSeq-local, non-blocking poll)
# ----------------------------------------------------------------------

def _open_stepseq_midi_input():
    """
    Try to open a MIDI input port for StepSeq live pad input.

    Selection priority:
      1) If env APS_STEPSEQ_MIDI_IN is set: pick the first port containing that substring (case-insensitive)
      2) If a port contains 'MPK' or 'AKAI': pick it
      3) Fallback: first available port
    """
    if mido is None:
        return None
    try:
        names = list(mido.get_input_names())
    except Exception:
        names = []
    if not names:
        return None

    want = (os.environ.get("APS_STEPSEQ_MIDI_IN") or "").strip()
    pick = None

    if want:
        w = want.lower()
        for n in names:
            if w in n.lower():
                pick = n
                break

    if pick is None:
        for n in names:
            ln = n.lower()
            if ("mpk" in ln) or ("akai" in ln):
                pick = n
                break

    if pick is None:
        pick = names[0]

    try:
        return mido.open_input(pick)
    except Exception:
        return None



# ----------------------------------------------------------------------
# MIDI input presence heuristic (pad/controller attached?)
# ----------------------------------------------------------------------

def _detect_stepseq_pad_present(input_names: Optional[List[str]] = None) -> bool:
    """
    Heuristic: determine whether an external pad/controller is present.

    Rationale (MVP-1):
      - When a pad/controller is connected, StepSeq should NOT auto-open GS Wavetable.
      - When no external input exists (keyboard-only StepSeq), keep legacy GS-friendly behavior.
    """
    if mido is None:
        return False
    try:
        names = list(input_names) if input_names is not None else list(mido.get_input_names())
    except Exception:
        names = []
    if not names:
        return False

    # If user explicitly selected a MIDI IN port, assume an external device is intended.
    if (os.environ.get("APS_STEPSEQ_MIDI_IN") or "").strip():
        return True

    # Common substrings for pads/controllers (keep it simple & robust)
    KEYWORDS = (
        "mpk", "akai", "pad", "controller", "launchpad", "maschine", "apc",
        "drum", "beat", "keylab", "oxygen", "novation", "arturia"
    )
    for n in names:
        ln = (n or "").lower()
        if any(k in ln for k in KEYWORDS):
            return True
    return False

# ----------------------------------------------------------------------
# MIDI live output helpers (optional, for audition / preview)
# ----------------------------------------------------------------------

def _open_stepseq_midi_output(pad_present: bool = False):
    """
    Try to open a MIDI output port for StepSeq audition / preview and StepSeq-local playback.

    Policy (MVP-1):
      - If a pad/controller is present (pad_present=True):
          * Never auto-open "Microsoft GS Wavetable Synth".
          * Use only APS_STEPSEQ_MIDI_OUT if provided; otherwise, keep output disabled (None).
      - If no external input is present (pad_present=False, keyboard-only StepSeq):
          * If APS_STEPSEQ_MIDI_OUT is provided: use it.
          * Otherwise: allow GS Wavetable as a convenience default (legacy behavior).

    Notes:
      - StepSeq must keep working without MIDI OUT (preview/playback become silent).
      - We intentionally avoid "best guess" auto-selection when a pad is present to
        prevent noisy WinMM backend errors on Windows.
    """
    if mido is None:
        return None
    try:
        names = list(mido.get_output_names())
    except Exception:
        names = []
    if not names:
        return None

    want = (os.environ.get("APS_STEPSEQ_MIDI_OUT") or "").strip()
    pick = None

    def _is_gs_wavetable(port_name: str) -> bool:
        ln = (port_name or "").lower()
        return ("microsoft gs" in ln) or ("wavetable" in ln)

    # 1) Explicit env selection always wins (substring match)
    if want:
        w = want.lower()
        for n in names:
            if w in (n or "").lower():
                pick = n
                break
        if pick is None:
            # If explicitly requested but not found, keep silent.
            return None

    # 2) No env selection: choose according to pad_present policy
    if pick is None:
        if pad_present:
            return None  # do not auto-open anything when a pad/controller is present
        # keyboard-only: allow GS as a reasonable default if available
        for n in names:
            if _is_gs_wavetable(n):
                pick = n
                break
        if pick is None:
            return None

    try:
        return mido.open_output(pick)
    except Exception:
        # Some backends print noisy WinMM errors even if we catch exceptions.
        # Treat as "no output" and keep StepSeq running.
        return None
    try:
        names = list(mido.get_output_names())
    except Exception:
        names = []
    if not names:
        return None

    want = (os.environ.get("APS_STEPSEQ_MIDI_OUT") or "").strip()
    pick = None

    # Safe default: do not auto-open any output port unless explicitly requested.
    # This avoids noisy WinMM errors on systems where only "Microsoft GS Wavetable Synth" exists.
    if not want:
        return None

    if want:
        w = want.lower()
        for n in names:
            if w in n.lower():
                pick = n
                break

    def _is_gs_wavetable(port_name: str) -> bool:
        ln = (port_name or "").lower()
        return ("microsoft gs" in ln) or ("wavetable" in ln)

    if pick is None:
        # Safe default: do not auto-select any MIDI output unless explicitly configured.
        return None

    try:
        return mido.open_output(pick)
    except Exception:
        # Some backends print noisy WinMM errors even if we catch exceptions.
        # Treat as "no output" and keep StepSeq running.
        return None

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

    # --- StepSeq live input state (MVP-1) ---
    # REC armed: when ON, incoming MIDI NoteOn will stamp into current cursor step.
    rec_armed = False
    advance_step_on_hit = True  # step-recording feel
    midi_in = _open_stepseq_midi_input()
    midi_ok = bool(midi_in)

    # Detect whether an external pad/controller is present (affects MIDI OUT policy)
    pad_present = _detect_stepseq_pad_present()

    midi_out = _open_stepseq_midi_output(pad_present=pad_present)
    midi_out_ok = bool(midi_out)

    status_msg = ""
    status_msg_until = 0.0

    # Non-blocking keyboard so we can poll MIDI in the same loop.
    try:
        stdscr.nodelay(True)
    except Exception:
        pass


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

    # Enter key will write notes using this accent level (1=SOFT, 2=MEDIUM, 3=STRONG)
    enter_accent_level = 2

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

    # --- MVP-2: metronome + non-blocking playback loop ---
    metro_on = False
    playing = False
    play_step = 0
    next_step_t = 0.0
    gate_sec = 0.030  # short drum gate

    # Input snap window (msec) around step boundaries.
    # If a hit arrives within this window at the very start of a step, snap to the previous step.
    # If it arrives within this window at the very end of a step, snap to the next step.
    SNAP_MS = 40  # symmetric early/late tolerance for human timing

    # Recording timing offset (msec). Negative = stamp slightly earlier.
    # This compensates for consistent human/chain latency so hits land on the intended grid.
    RECORD_OFFSET_MS = -25

    # When playing, monitoring the input can double-trigger against the sequenced hit.
    # Reduce monitoring velocity slightly to keep the feel without smearing timing.
    MONITOR_PLAY_GAIN = 0.70

    # MVP-2.6: loop scope + count-in (simple, no option sprawl)
    # - Default loop is the *current bar* (bar-local loop), which greatly improves overdub feel.
    # - When REC is armed and playback starts, we run a 1-bar count-in (click only, no stamping).
    LOOP_BAR_DEFAULT = False
    COUNTIN_BARS = 1  # fixed 1-bar count-in for MVP

    loop_bar = LOOP_BAR_DEFAULT
    loop_bar_user_override = False  # becomes True after user presses 'b'
    loop_start = 0
    loop_end = int(grid.steps)

    countin_remaining_steps = 0
    countin_step = 0


    # Metronome click (GM-ish defaults)
    CLICK_NOTE = 37  # Rim/Side Stick (works well on GS + many modules)
    CLICK_VEL_STRONG = 100
    CLICK_VEL_WEAK = 60

    beats_per_bar = 4
    spb_local = int(getattr(meta, "steps_per_bar", 16) or 16)
    if spb_local <= 0:
        spb_local = max(1, grid.steps // 2)
    beat_len = (spb_local // beats_per_bar) if (spb_local % beats_per_bar == 0) else None

    bpm_local = int(getattr(meta, "bpm", 120) or 120)
    if bpm_local <= 0:
        bpm_local = 120
    sec_per_step = (60.0 / float(bpm_local)) * (float(beats_per_bar) / float(spb_local))

    # Pending note-offs (min-heap): (off_time_monotonic, note_int)
    pending_note_off = []


    # ------------------------------------------------------------------
    # StepSeq UI helpers (status + audition) and slot/empty-lane policy
    # ------------------------------------------------------------------

    def _set_status(msg: str, duration_sec: float = 1.2):
        nonlocal status_msg, status_msg_until
        status_msg = str(msg or "")
        status_msg_until = time.time() + float(duration_sec)

    def _status_now() -> str:
        if status_msg and (time.time() <= status_msg_until):
            return status_msg
        return ""

    # Core lanes are protected from reassignment (editor policy)
    CORE_ABBR = {"KK", "SN", "CH", "OH"}

    # Reference map for new lanes (2-letter abbr + <=6 label)
    REF_NOTE_MAP = {
        36: ("KK", "KICK"),
        38: ("SN", "SNARE"),
        42: ("CH", "HH_CL"),
        46: ("OH", "HH_OP"),
        47: ("MT", "TOM_M"),
        45: ("LT", "TOM_L"),
        50: ("HT", "TOM_H"),
        49: ("CR", "CRASH"),
        51: ("RD", "RIDE"),
        39: ("CL", "CLAP"),
        54: ("TA", "TAMB"),
        56: ("CB", "COWBL"),
        37: ("RM", "RIM"),
        82: ("SH", "SHAKR"),
        76: ("HW", "WBLK_H"),
        55: ("SP", "SPLASH"),
        44: ("PH", "HH_PED"),
    }

    def _preview_note(note: int, vel: int):
        """Play a very short audition note (if MIDI OUT is available)."""
        # During PLAY, monitoring/audition causes double-trigger with sequencer playback.
        # Disable it for stable real-time recording.
        if playing:
            return
        if midi_out is None or mido is None:
            return
        try:
            n = int(note)
            v = int(vel)
        except Exception:
            return
        if n <= 0 or v <= 0:
            return
        try:
            midi_out.send(mido.Message("note_on", channel=int(meta.channel), note=n, velocity=v))
            time.sleep(0.03)
            midi_out.send(mido.Message("note_off", channel=int(meta.channel), note=n, velocity=0))
        except Exception:
            pass


    def _monitor_hit(note: int, vel: int, now_t: float) -> None:
        """Non-blocking monitoring: send note_on + scheduled note_off."""
        if playing:
            return
        if midi_out is None or mido is None:
            return
        try:
            n = int(note)
            v = int(vel)
            # Slightly attenuate monitoring while playing to reduce double-trigger smear.
            if playing:
                try:
                    v = max(1, int(round(v * float(MONITOR_PLAY_GAIN))))
                except Exception:
                    v = v
        except Exception:
            return
        if n <= 0 or v <= 0:
            return
        if _send_note_on(n, v):
            _schedule_note_off(n, float(now_t) + gate_sec)

    def _pick_input_step(now_t: float) -> int:
        """Choose the best target step for an input hit.

        We treat the grid (step index) as authoritative, but compensate for
        consistent latency and human timing drift:

        - Apply RECORD_OFFSET_MS (negative stamps slightly earlier)
        - If the adjusted hit falls near the step start, snap to previous
        - If it falls near the step end, snap to next
        """
        if not playing:
            return int(cur_step)

        try:
            sp = float(sec_per_step)
            if sp <= 0:
                return int(cur_step)

            # Step start time for the *current* step (cur_step).
            step_start_t = float(next_step_t) - sp

            # Apply constant offset to compensate for consistent latency.
            t_eff = float(now_t) + (float(RECORD_OFFSET_MS) / 1000.0)

            # Phase relative to current step start (can be <0 or >sp due to offset).
            phase = t_eff - step_start_t

            # Clamp snap window to < half-step to avoid pathological snapping.
            snap = min(float(SNAP_MS) / 1000.0, sp * 0.45)

            # Snap logic (symmetric): near start => previous, near end => next.
            if phase < snap:
                return (int(cur_step) - 1) % int(grid.steps)
            if phase > (sp - snap):
                return (int(cur_step) + 1) % int(grid.steps)
        except Exception:
            pass

        return int(cur_step)


    def _send_note_on(note: int, vel: int) -> bool:
        if midi_out is None or mido is None:
            return False
        try:
            midi_out.send(mido.Message("note_on", channel=int(meta.channel), note=int(note), velocity=int(vel)))
            return True
        except Exception:
            return False

    def _send_note_off(note: int) -> None:
        if midi_out is None or mido is None:
            return
        try:
            midi_out.send(mido.Message("note_off", channel=int(meta.channel), note=int(note), velocity=0))
        except Exception:
            pass

    def _schedule_note_off(note: int, off_time: float) -> None:
        try:
            heapq.heappush(pending_note_off, (float(off_time), int(note)))
        except Exception:
            pass

    def _process_pending_note_off(now_t: float) -> None:
        while pending_note_off and pending_note_off[0][0] <= now_t:
            _t, n = heapq.heappop(pending_note_off)
            _send_note_off(n)

    def _tick_playback(now_t: float) -> None:
        nonlocal play_step, next_step_t, cur_step, page, loop_start, loop_end, countin_remaining_steps, countin_step

        if (not playing) or (now_t < next_step_t):
            return

        # -----------------------------
        # Count-in: click only, no grid playback, no stamping
        # -----------------------------
        if countin_remaining_steps > 0:
            if midi_out is not None and mido is not None:
                vel = None
                # Strong click on bar start of count-in
                if (countin_step % spb_local) == 0:
                    vel = CLICK_VEL_STRONG
                # Weak click on beat boundaries
                elif beat_len is not None and (countin_step % beat_len) == 0:
                    vel = CLICK_VEL_WEAK
                if vel is not None:
                    if _send_note_on(CLICK_NOTE, int(vel)):
                        _schedule_note_off(CLICK_NOTE, now_t + gate_sec)

            countin_remaining_steps -= 1
            countin_step += 1

            # Keep cursor parked at loop start during count-in (stable visual anchor)
            cur_step = int(loop_start)
            page = cur_step // page_size

            # When count-in finishes, start actual loop at loop_start
            if countin_remaining_steps <= 0:
                play_step = int(loop_start)
                cur_step = int(loop_start)
                page = cur_step // page_size

            # Schedule next tick (drift-safe)
            next_step_t = next_step_t + sec_per_step
            if next_step_t < now_t - sec_per_step:
                next_step_t = now_t + sec_per_step
            return

        # -----------------------------
        # Normal playback: fire grid notes at current play_step
        # -----------------------------
        if midi_out is not None and mido is not None:
            for ln in grid.lanes:
                cell = ln.cells[play_step]
                if not cell.on:
                    continue
                v = int(cell.vel or 0)
                if v <= 0:
                    continue
                n = int(ln.note)
                if _send_note_on(n, v):
                    _schedule_note_off(n, now_t + gate_sec)

            # Metronome click (if enabled)
            if metro_on:
                vel = None
                if play_step % spb_local == 0:
                    vel = CLICK_VEL_STRONG
                elif beat_len is not None and (play_step % beat_len == 0):
                    vel = CLICK_VEL_WEAK
                if vel is not None:
                    if _send_note_on(CLICK_NOTE, int(vel)):
                        _schedule_note_off(CLICK_NOTE, now_t + gate_sec)

        # Keep cursor synced to the *current* playhead step (the one we just fired)
        cur_step = int(play_step)
        page = cur_step // page_size

        # Advance playhead for the next tick (loop current bar by default)
        play_step = int(play_step) + 1
        if loop_bar:
            if play_step >= loop_end:
                play_step = int(loop_start)
        else:
            if play_step >= int(grid.steps):
                play_step = 0

        # Schedule next tick (drift-safe)
        next_step_t = next_step_t + sec_per_step
        if next_step_t < now_t - sec_per_step:
            next_step_t = now_t + sec_per_step
    def _lane_is_empty(lane: StepLane) -> bool:
        for c in lane.cells:
            if getattr(c, "on", False):
                return False
        return True

    def _has_empty_reassignable_lane() -> bool:
        """StepSeq-side approximation of main's 'empty slot exists' rule."""
        for ln in grid.lanes:
            nm = (ln.name or "").strip()
            if nm in CORE_ABBR:
                continue
            if _lane_is_empty(ln):
                return True
        return False

    def _ensure_lane_for_note(note: int) -> int:
        """
        Return lane index for note.

        MVP-1 policy alignment with aps_main slot reassignment:
          - If note already exists in lanes: return its lane index.
          - If note is new:
              * Reuse the first completely empty NON-CORE lane as a "reassigned slot".
              * If no such lane exists, return -1 (caller should reject).
        """
        n = int(note)
        for li, ln in enumerate(grid.lanes):
            if int(getattr(ln, "note", -9999)) == n:
                return li

        # Find an empty, reassignable (non-core) lane to redefine
        for li, ln in enumerate(grid.lanes):
            nm = (ln.name or "").strip()
            if nm in CORE_ABBR:
                continue
            if _lane_is_empty(ln):
                abbr, _lbl = REF_NOTE_MAP.get(n, (f"N{n}", f"NOTE{n}"))
                ln.name = abbr
                ln.note = n
                # cells are already empty by definition, but keep it explicit/safe
                for c in ln.cells:
                    c.on = False
                    c.vel = 0
                return li

        return -1

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

        rec_txt = "ON" if rec_armed else "OFF"
        midi_txt = ("IN:" + ("OK" if midi_ok else "NA") + " OUT:" + ("OK" if midi_out_ok else "NA") + " PAD:" + ("Y" if pad_present else "N") + " PLAY:" + ("Y" if playing else "N") + " METRO:" + ("Y" if metro_on else "N") + " LOOP:" + ("BAR" if loop_bar else "FULL") + (" CIN" if (countin_remaining_steps > 0) else ""))

        header = (
            "[STEP] {name}  CH={ch}  LEN={bars}bar  STEPS={steps}  BPM={bpm}  MOD={mod}  REC={rec}  MIDI={midi}"
            .format(
                name=(meta.name + ('*' if modified else '')),
                ch=meta.channel + 1,
                bars=meta.bars,
                steps=grid.steps,
                bpm=meta.bpm,
                mod="Y" if modified else "N",
                rec=rec_txt,
                midi=midi_txt,
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

                col += 3

        # Velocity legend (symbol uses same accent background style; text stays normal)
        try:
            y_leg = max_y - 5
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
            _draw_leg("-", P_CURSOR_L1, "SOFT"   + ("*" if enter_accent_level == 1 else ""))
            _draw_leg("X", P_CURSOR_L2, "MEDIUM" + ("*" if enter_accent_level == 2 else ""))
            _draw_leg("O", P_CURSOR_L3, "STRONG" + ("*" if enter_accent_level == 3 else ""))
        except curses.error:
            pass

        # Status line (transient)
        try:
            y_stat = max_y - 4
            msg = _status_now()
            if msg:
                stdscr.addnstr(y_stat, 2, msg.ljust(max_x - 4), max_x - 4, curses.A_BOLD)
            else:
                stdscr.addnstr(y_stat, 2, " ".ljust(max_x - 4), max_x - 4)
        except curses.error:
            pass


        footer = "Move: arrows/h/j/k/l  Enter:write accent / toggle off  A:accent  J/K:vel  r:REC(arm)  [ ]:bar  c:copy bar1->bar2  Shift+B:clr bar  Shift+R:clr row  Shift+C:clr col  Space:play/stop  b:loop  m:metro  w:save  q/Esc:exit"
        # Footer can be long; wrap it to the window width (2 lines reserved)
        footer_y = max_y - 3
        footer_w = max(1, max_x - 2)
        lines = textwrap.wrap(footer, width=footer_w, break_long_words=False, break_on_hyphens=False)
        for i in range(2):
            if footer_y + i >= max_y - 1:
                break
            line = lines[i] if i < len(lines) else ""
            try:
                stdscr.addnstr(footer_y + i, 1, line.ljust(footer_w), footer_w)
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

        now_t = time.monotonic()
        _process_pending_note_off(now_t)
        _tick_playback(now_t)

        # Poll MIDI (non-blocking). When REC armed, NoteOn stamps into current cursor step.
        # Poll MIDI (non-blocking).
        # - REC=OFF: preview-only (sound only if MIDI OUT is available), no grid changes.
        # - REC=ON : stamp into current playhead step.
        midi_hit = False
        if midi_in is not None:
            try:
                for msg in midi_in.iter_pending():
                    if getattr(msg, "type", None) != "note_on":
                        continue
                    vel = int(getattr(msg, "velocity", 0) or 0)
                    if vel <= 0:
                        continue

                    note = int(getattr(msg, "note", -1))

                    if not rec_armed:
                        # Friendly preview while not recording
                        now_t = time.monotonic()
                        _monitor_hit(note, vel, now_t)
                        _set_status(f"PREVIEW NOTE {note}  vel={vel}", duration_sec=0.6)
                        midi_hit = True
                        continue

                    # REC armed: allow stamping.
                    # During count-in, do NOT stamp; preview/monitor only.
                    if countin_remaining_steps > 0:
                        now_t = time.monotonic()
                        _monitor_hit(note, vel, now_t)
                        _set_status("COUNT-IN (no recording)", duration_sec=0.6)
                        midi_hit = True
                        continue

                    # If note is not in lanes yet, allow only if an empty reassignable lane exists (core excluded).
                    lane_exists = any(int(getattr(ln, "note", -9999)) == note for ln in grid.lanes)
                    if (not lane_exists) and (not _has_empty_reassignable_lane()):
                        now_t = time.monotonic()
                        _monitor_hit(note, vel, now_t)
                        _set_status(f"NO EMPTY SLOT (NOTE {note})", duration_sec=1.2)
                        midi_hit = True
                        continue

                    lane_idx = _ensure_lane_for_note(note)
                    if lane_idx < 0:
                        now_t = time.monotonic()
                        _monitor_hit(note, vel, now_t)
                        _set_status(f"NO EMPTY SLOT (NOTE {note})", duration_sec=1.2)
                        midi_hit = True
                        continue

                    # Monitor / audition input while recording as well (MVP-2 UX):
                    # Non-blocking monitor + symmetric early/late snap to the nearest intended step.
                    now_t = time.monotonic()
                    target_step = _pick_input_step(now_t)
                    cell = grid.lanes[lane_idx].cells[target_step]
                    _monitor_hit(note, vel, now_t)
                    cell.on = True
                    cell.vel = max(int(getattr(cell, "vel", 0) or 0), int(vel))
                    modified = True
                    midi_hit = True

                    if advance_step_on_hit and (not playing):
                        cur_step = (cur_step + 1) % grid.steps
            except Exception:
                # If MIDI port dies, disable it silently (MVP-friendly)
                try:
                    midi_in.close()
                except Exception:
                    pass
                midi_in = None
                midi_ok = False
        # Avoid busy-loop when no key and no MIDI
        if key == -1 and not midi_hit:
            # If playing, don't oversleep past the next step time.
            if playing:
                now2 = time.monotonic()
                dt = max(0.0, next_step_t - now2)
                time.sleep(min(0.005, dt))
            else:
                time.sleep(0.005)
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

        elif key == ord("r"):
            # StepSeq live input: toggle REC(arm)
            rec_armed = not rec_armed

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

        elif key == ord("\n"):  # Enter
            lane = grid.lanes[cur_lane]
            cell = lane.cells[cur_step]
            if cell.on:
                # Enter toggles OFF when a note already exists
                cell.on = False
                cell.vel = 0
            else:
                # Enter writes a note using the current input accent (SOFT/MEDIUM/STRONG)
                cell.on = True
                cell.vel = level_to_vel(enter_accent_level)
                # Friendly audition on creation
                _preview_note(lane.note, cell.vel)
            modified = True

        elif key in (ord('a'), ord('A')):  # Shift+A: cycle Enter input accent (SOFT -> MEDIUM -> STRONG)
            if enter_accent_level == 1:
                enter_accent_level = 2
            elif enter_accent_level == 2:
                enter_accent_level = 3
            else:
                enter_accent_level = 1
            # No data modified yet; just UI state
        elif key in (ord('K'), ord('.')):  # Shift+K: stronger (vim-style, non-cycling)
            cell = grid.lanes[cur_lane].cells[cur_step]
            if cell.on:
                lvl = vel_to_level(cell.vel)
                if lvl < 1:
                    lvl = 2
                lvl = _adjust_level_1_3(lvl, +1)
                cell.vel = level_to_vel(lvl)
                modified = True
                _preview_note(grid.lanes[cur_lane].note, cell.vel)
        elif key in (ord('J'), ord(',')):  # Shift+J: weaker (vim-style, non-cycling)
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

        # ------------------------------------------------------------
        # StepSeq matrix edit (Shift+B/R/C)
        # - Shift+B: clear current bar (page)
        # - Shift+R: clear current row (instrument lane) within current bar
        # - Shift+C: clear current column (step) within current bar
        # NOTE: These are StepSeq-local keys.
        # ------------------------------------------------------------
        elif key == ord('B'):  # Shift+B: clear current bar
            start = page * page_size
            end = min(start + page_size, grid.steps)
            for lane in grid.lanes:
                for s in range(start, end):
                    lane.cells[s].on = False
                    lane.cells[s].vel = 0
            modified = True

        elif key == ord('R'):  # Shift+R: clear current row (lane) in current bar
            start = page * page_size
            end = min(start + page_size, grid.steps)
            lane = grid.lanes[cur_lane]
            for s in range(start, end):
                lane.cells[s].on = False
                lane.cells[s].vel = 0
            modified = True

        elif key == ord('C'):  # Shift+C: clear current column (step) in current bar
            # Guard: only apply when cursor step is inside current bar page
            start = page * page_size
            end = min(start + page_size, grid.steps)
            if start <= cur_step < end:
                for lane in grid.lanes:
                    lane.cells[cur_step].on = False
                    lane.cells[cur_step].vel = 0
                modified = True

        elif key == ord("c"):
            # Copy bar1 -> bar2 (page_size steps) when bar2 exists
            if grid.steps >= 2 * page_size:
                for lane in grid.lanes:
                    for i in range(page_size):
                        src = lane.cells[i]
                        dst = lane.cells[i + page_size]
                        dst.on = src.on
                        dst.vel = src.vel
                modified = True


        elif key in (ord("m"), ord("M")):
            metro_on = not metro_on
            if metro_on:
                if midi_out is None:
                    _set_status("METRO ON (muted: no MIDI OUT)", duration_sec=1.2)
                else:
                    _set_status("METRO ON", duration_sec=0.8)
            else:
                _set_status("METRO OFF", duration_sec=0.6)

        elif key in (ord("b"), ord("B")):
            loop_bar_user_override = True
            loop_bar = not loop_bar
            if loop_bar:
                _set_status("LOOP BAR", duration_sec=0.7)
            else:
                _set_status("LOOP FULL", duration_sec=0.7)

        elif key == 32:  # Space
            # MVP-2.6: toggle playback loop (non-blocking), default loop is the *current bar*.
            playing = not playing
            if playing:
                # Auto loop policy:
                # - Default (REC OFF): FULL loop
                # - When REC is armed and playback starts: BAR loop (unless user explicitly toggled with 'b')
                if rec_armed and (not loop_bar_user_override):
                    loop_bar = True

                # Determine loop scope
                if loop_bar:
                    try:
                        loop_start = (int(cur_step) // int(spb_local)) * int(spb_local)
                    except Exception:
                        loop_start = 0
                    loop_end = int(loop_start) + int(spb_local)
                    if loop_end > int(grid.steps):
                        loop_end = int(grid.steps)
                else:
                    loop_start = 0
                    loop_end = int(grid.steps)

                play_step = int(loop_start)
                cur_step = int(loop_start)
                page = cur_step // page_size

                # 1-bar count-in when REC is armed (click only; stamping disabled during count-in)
                if rec_armed and COUNTIN_BARS > 0:
                    countin_remaining_steps = int(spb_local) * int(COUNTIN_BARS)
                    countin_step = 0
                else:
                    countin_remaining_steps = 0
                    countin_step = 0

                next_step_t = time.monotonic()

                if midi_out is None:
                    if pad_present:
                        _set_status("PLAY muted (set APS_STEPSEQ_MIDI_OUT)", duration_sec=1.2)
                    else:
                        _set_status("PLAY muted (no MIDI OUT)", duration_sec=1.2)
                else:
                    if countin_remaining_steps > 0:
                        _set_status("PLAY (count-in 1bar)", duration_sec=0.9)
                    else:
                        _set_status("PLAY", duration_sec=0.6)
            else:
                # Stop: flush any pending note-offs immediately
                try:
                    while pending_note_off:
                        _t, n = heapq.heappop(pending_note_off)
                        _send_note_off(n)
                except Exception:
                    pass
                countin_remaining_steps = 0
                countin_step = 0
                _set_status("STOP", duration_sec=0.6)

            # Drain queued keys (esp. Space)
            try:
                stdscr.nodelay(True)
                while True:
                    k2 = stdscr.getch()
                    if k2 == -1:
                        break
            except curses.error:
                pass

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

    # Close StepSeq MIDI ports (optional)
    try:
        if midi_in is not None:
            midi_in.close()
    except Exception:
        pass
    try:
        if midi_out is not None:
            midi_out.close()
    except Exception:
        pass

    new_events = _apply_stepgrid_to_events(grid, meta, non_grid)
    return modified, saved, new_events
