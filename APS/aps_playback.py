# aps_playback.py — pattern & chain playback for APS v0.27
import time
import os
from typing import List

import mido

from aps_core import Pattern, ChainEntry, compute_timing
from aps_ui import draw_grid


def velocity_from_acc(a: int) -> int:
    """Map APS accent level (0..3) to MIDI velocity.

    ADT v2.2a encodes relative dynamics only; APS uses a stable default mapping.
    """
    if a <= 0:
        return 0
    if a == 1:
        return 50
    if a == 2:
        return 90
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
    gate = min(step_sec * 0.6, 0.08)

    stdscr.nodelay(True)
    try:
        for step in range(p.length):
            try:
                ch = stdscr.getch()
                if ch == ord(' '):
                    raise KeyboardInterrupt
            except Exception:
                pass

            draw_grid(p, grid_win, step, use_color, color_pairs)
            stdscr.refresh()

            active = []
            for slot in range(p.slots):
                acc = p.grid[step][slot]
                vel = velocity_from_acc(acc)
                if vel > 0:
                    note = p.slot_note[slot]
                    msg_on = mido.Message('note_on', note=note, velocity=vel, channel=9)
                    active.append(msg_on)
                    out.send(msg_on)

            time.sleep(gate)

            for msg_on in active:
                out.send(mido.Message('note_off', note=msg_on.note, velocity=0, channel=msg_on.channel))

            rest = step_sec - gate
            t0 = time.time()
            while time.time() - t0 < rest:
                try:
                    ch = stdscr.getch()
                    if ch == ord(' '):
                        raise KeyboardInterrupt
                except Exception:
                    pass
                time.sleep(0.002)
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
) -> int:
    if not chain:
        return start_index
    if start_index < 0:
        start_index = 0
    if start_index >= len(chain):
        start_index = 0

    out = mido.open_output(midi_port)
    out.send(mido.Message('control_change', control=123, value=0, channel=9))
    time.sleep(0.03)

    try:
        for i in range(start_index, len(chain)):
            entry = chain[i]
            from aps_ui import draw_chain_view  # local import to avoid cycle
            from aps_sections import ChainSelection, SectionManager
            draw_chain_view(chain_win, chain, True, i, ChainSelection(), SectionManager(), "")
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
        out.close()
