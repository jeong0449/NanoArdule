# aps_playback.py — pattern & chain playback for APS v0.27
import time
import os
from typing import List

import mido

from aps_core import Pattern, ChainEntry, compute_timing
from aps_ui import draw_grid

from aps_sections import ChainSelection, SectionManager
# Reusable dummy objects for drawing (do not recreate every frame)
_DUMMY_SELECTION = ChainSelection()
_DUMMY_SECTION_MGR = SectionManager()



def velocity_from_acc(a: int) -> int:
    if a <= 0:
        return 0
    if a == 1:
        return 80
    if a == 2:
        return 100
    return 120

def play_pattern_on_output(
    p: Pattern,
    bpm: int,
    out,
    stdscr,
    grid_win,
    use_color,
    color_pairs,
):
    beats, bars, spb, spbar = compute_timing(p)
    total_beats = beats * bars if beats else 4
    sec_per_beat = 60.0 / bpm
    step_sec = (total_beats * sec_per_beat) / p.length

    # Gate must never exceed step duration
    gate = min(step_sec * 0.6, 0.08)
    if gate > step_sec:
        gate = step_sec

    def _poll_space_to_stop():
        """Return True if user pressed Space (stop)."""
        try:
            ch = stdscr.getch()
            return (ch == ord(" "))
        except Exception:
            return False

    stdscr.nodelay(True)
    try:
        # Absolute-time scheduler (prevents cumulative drift)
        t_start = time.perf_counter()
        t_step = t_start  # scheduled start time of current step

        for step in range(p.length):
            # Stop check (non-blocking)
            if _poll_space_to_stop():
                raise KeyboardInterrupt

            draw_grid(p, grid_win, step, use_color, color_pairs)
            stdscr.refresh()

            # NOTE ON
            active = []
            for slot in range(p.slots):
                acc = p.grid[step][slot]
                vel = velocity_from_acc(acc)
                if vel > 0:
                    note = p.slot_note[slot]
                    msg_on = mido.Message("note_on", note=note, velocity=vel, channel=9)
                    active.append(msg_on)
                    out.send(msg_on)

            # Hold notes until gate end (absolute time)
            t_gate_end = t_step + gate
            while True:
                if _poll_space_to_stop():
                    raise KeyboardInterrupt
                now = time.perf_counter()
                if now >= t_gate_end:
                    break
                # Sleep in small chunks; absolute schedule prevents drift anyway
                time.sleep(min(0.001, t_gate_end - now))

            # NOTE OFF
            for msg_on in active:
                out.send(mido.Message("note_off", note=msg_on.note, velocity=0, channel=msg_on.channel))

            # Schedule next step (absolute time)
            t_step += step_sec
            while True:
                if _poll_space_to_stop():
                    raise KeyboardInterrupt
                now = time.perf_counter()
                if now >= t_step:
                    break
                time.sleep(min(0.001, t_step - now))

    finally:
        stdscr.nodelay(False)


def play_pattern_in_grid(
    p: Pattern,
    bpm: int,
    midi_port: str,
    stdscr,
    grid_win,
    use_color,
    color_pairs,
    repeat_mode: bool,
):
    out = mido.open_output(midi_port)
    out.send(mido.Message('control_change', control=123, value=0, channel=9))
    time.sleep(0.03)
    try:
        while True:
            try:
                play_pattern_on_output(p, bpm, out, stdscr, grid_win, use_color, color_pairs)
            except KeyboardInterrupt:
                break
            if not repeat_mode:
                break
    finally:
        out.close()


def play_chain(
    chain: List[ChainEntry],
    bpm: int,
    midi_port: str,
    stdscr,
    grid_win,
    chain_win,
    root: str,
    use_color,
    color_pairs,
    start_index: int,
    load_pattern_func,
    out=None,
) -> int:
    if not chain:
        return start_index
    if start_index < 0:
        start_index = 0
    if start_index >= len(chain):
        start_index = 0

    opened_here = False
    if out is None:
        out = mido.open_output(midi_port)
        out.send(mido.Message('control_change', control=123, value=0, channel=9))
        time.sleep(0.03)
        opened_here = True

    try:
        for i in range(start_index, len(chain)):
            entry = chain[i]
            from aps_ui import draw_chain_view  # local import to avoid cycle
            from aps_sections import ChainSelection, SectionManager
            draw_chain_view(chain_win, chain, len(chain), True, i, _DUMMY_SELECTION, _DUMMY_SECTION_MGR, "")
            stdscr.refresh()

            path = os.path.join(root, entry.filename)
            if not os.path.isfile(path):
                continue

            try:
                p = load_pattern_func(path)
            except Exception:
                continue

            for _ in range(entry.repeats):
                try:
                    play_pattern_on_output(p, bpm, out, stdscr, grid_win, use_color, color_pairs)
                except KeyboardInterrupt:
                    return i

        return len(chain) - 1 if chain else 0
    finally:
        if opened_here and out is not None:
            out.close()
