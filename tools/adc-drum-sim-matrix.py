#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-drum-sim-matrix.py — Similarity matrix for 2‑bar drum pattern MIDI files

What it does
- Converts each input MIDI pattern into a fixed-length binary vector:
  12 drum slots (Ardule 12-slot mapping) × N time columns (default: 32).
- Uses CH10 (MIDI channel 10, i.e. channel number 9) note_on events only.
- Computes two all-pairs (N×N) similarity matrices:
  - Hamming similarity
  - Cosine similarity
- Prints the matrices to stdout with an index → filename legend.

Examples
  python adc-drum-sim-matrix.py RCK_P001.MID RCK_P002.MID RCK_P003.MID
  python adc-drum-sim-matrix.py --cols 48 RCK_P*.MID

Requirements
- Python 3.8+
- mido (pip install mido)
"""


import argparse
import math
import glob
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import mido


# ---------------------------------------------------------------------------
# Drum slot mapping (Ardule 12-slot)
# ---------------------------------------------------------------------------

SLOT_LABELS = [
    "BD",   # 0
    "SD",   # 1
    "RS",   # 2
    "CP",   # 3
    "CH",   # 4
    "PH",   # 5
    "OH",   # 6
    "LT",   # 7
    "HT",   # 8
    "CR",   # 9
    "RD",   #10
    "PER",  #11
]
N_SLOTS = len(SLOT_LABELS)


def note_to_slot(note: int) -> Optional[int]:
    """
    Map GM drum note (35–81) into Ardule 12-category slot index.
    """
    # 0: BD (Kick)
    if note in (35, 36):
        return 0

    # 1: SD (Snare)
    if note in (38, 40):
        return 1

    # 2: RS (Side Stick)
    if note == 37:
        return 2

    # 3: CP (Hand Clap)
    if note == 39:
        return 3

    # 4: CH (Closed Hi-Hat)
    if note == 42:
        return 4

    # 5: PH (Pedal Hi-Hat)
    if note == 44:
        return 5

    # 6: OH (Open Hi-Hat)
    if note == 46:
        return 6

    # 7: LT (Low/Low-mid toms)
    if note in (41, 45, 47):
        return 7

    # 8: HT (Mid/High toms)
    if note in (43, 48, 50):
        return 8

    # 9: CR (Crash-like cymbals)
    if note in (49, 52, 55, 57):
        return 9

    # 10: RD (Ride cymbals and bell)
    if note in (51, 53, 59):
        return 10

    # 11: PER (Percussion bucket: Cowbell + Latin / FX)
    if note == 56 or (60 <= note <= 81):
        return 11

    return None


# ---------------------------------------------------------------------------
# MIDI helpers
# ---------------------------------------------------------------------------

def build_absolute_track(track: mido.MidiTrack) -> List[mido.Message]:
    """Convert delta-time track into absolute-time messages."""
    out: List[mido.Message] = []
    t = 0
    for msg in track:
        t += msg.time
        out.append(msg.copy(time=t))
    return out


def current_time_signature(track: mido.MidiTrack, abs_tick: int, ticks_per_beat: int) -> Tuple[int, int]:
    """Return (numerator, denominator) at given absolute tick."""
    num, den = 4, 4
    t = 0
    for msg in track:
        t += msg.time
        if t > abs_tick:
            break
        if msg.type == 'time_signature':
            num = msg.numerator
            den = msg.denominator
    return num, den


def ticks_per_bar(tpb: int, num: int, den: int) -> int:
    """Calculate ticks per bar for given time signature."""
    return int(round(tpb * num * (4.0 / den)))


def build_events_by_tick(
    abs_msgs: List[mido.Message],
    start: int,
    end: int,
    channel: int = 9,
) -> Dict[int, Set[int]]:
    """Collect note_on events into a dict: tick -> set(note)."""
    events: Dict[int, Set[int]] = {}
    for m in abs_msgs:
        if start <= m.time < end:
            if m.type == 'note_on' and getattr(m, 'channel', None) == channel and m.velocity > 0:
                rel = m.time - start
                s = events.setdefault(rel, set())
                s.add(m.note)
    return events


# ---------------------------------------------------------------------------
# Vectorization & similarity
# ---------------------------------------------------------------------------

def build_binary_grid_from_midi(midi_path: Path, cols: int = 32) -> List[int]:
    """
    Convert a 2-bar drum pattern MIDI into a 12×cols binary grid (0/1),
    and return it as a flat vector of length 12*cols.
    - Use CH10 only (channel number 9).
    - Project notes into the 12-slot mapping via note_to_slot().
    - If any note exists at a slot/step, set it to 1.
    """
    mf = mido.MidiFile(midi_path)
    if mf.type not in (0, 1):
        raise SystemExit(f"Only Type 0 or 1 is supported: {midi_path}")

    # src_track: type 0이면 트랙1, type 1이면 merge
    if mf.type == 0:
        src_track = mf.tracks[0]
    else:
        src_track = mido.merge_tracks(mf.tracks)

    abs_msgs = build_absolute_track(src_track)
    if not abs_msgs:
        return [0] * (N_SLOTS * cols)

    tpq = mf.ticks_per_beat
    num0, den0 = current_time_signature(src_track, 0, tpq)
    bar_ticks = ticks_per_bar(tpq, num0, den0)

    # Assume a 2-bar pattern and use only the first two bars.
    length = 2 * bar_ticks
    start = 0
    end = start + length

    # ticks → set(notes)
    events_by_tick = build_events_by_tick(abs_msgs, start, end, channel=9)

    # 12×cols binary grid
    grid = [[0 for _ in range(cols)] for _ in range(N_SLOTS)]
    ticks_per_col = length / cols if cols > 0 else 1.0

    for t, notes in events_by_tick.items():
        col = int(round(t / ticks_per_col)) if ticks_per_col > 0 else 0
        if col < 0:
            col = 0
        if col >= cols:
            col = cols - 1
        for nt in notes:
            sl = note_to_slot(nt)
            if sl is None or not (0 <= sl < N_SLOTS):
                continue
            grid[sl][col] = 1  # 해당 슬롯/스텝에 노트가 하나라도 있으면 1

    # Row-major flatten → vector length N_SLOTS * cols
    vec: List[int] = []
    for sl in range(N_SLOTS):
        vec.extend(grid[sl])
    return vec


def hamming_distance(v1: List[int], v2: List[int]) -> int:
    """Hamming distance between two binary vectors."""
    if len(v1) != len(v2):
        raise ValueError("Vector length mismatch.")
    return sum(1 for a, b in zip(v1, v2) if a != b)


def hamming_similarity(v1: List[int], v2: List[int]) -> float:
    """Hamming-distance-based similarity (1.0 = identical)."""
    d = hamming_distance(v1, v2)
    return 1.0 - d / len(v1)


def cosine_similarity(v1: List[int], v2: List[int]) -> float:
    """Cosine similarity (1.0 = identical, 0 = orthogonal)."""
    if len(v1) != len(v2):
        raise ValueError("Vector length mismatch.")
    dot = sum(a * b for a, b in zip(v1, v2))
    n1 = math.sqrt(sum(a * a for a in v1))
    n2 = math.sqrt(sum(b * b for b in v2))
    if n1 == 0 or n2 == 0:
        return 0.0
    return dot / (n1 * n2)


# ---------------------------------------------------------------------------
# Matrix calculation & printing
# ---------------------------------------------------------------------------

def print_similarity_matrix(
    names: List[str],
    mat: List[List[float]],
    title: str,
) -> None:
    """
    Pretty-print a name list and an N×N similarity matrix.
    Use indices as headers and print an index → filename legend.
    """
    n = len(names)
    print()
    print("=" * 80)
    print(title)
    print("=" * 80)

    # 헤더: 열 인덱스
    header = "     " + "".join(f"{j:7d}" for j in range(n))
    print(header)
    for i in range(n):
        row_vals = "".join(f"{mat[i][j]:7.3f}" for j in range(n))
        print(f"{i:3d}: {row_vals}")

    print("\nIndex → Filename:")
    for i, nm in enumerate(names):
        print(f"  {i:3d}: {nm}")
    print()


def compute_and_print_matrices(paths: List[Path], cols: int = 32) -> None:
    if len(paths) < 2:
        raise SystemExit("Need at least 2 MIDI files to build a similarity matrix.")

    # Vectorize patterns
    names: List[str] = []
    vecs: List[List[int]] = []
    for p in paths:
        if not p.exists():
            raise SystemExit(f"File not found: {p}")
        v = build_binary_grid_from_midi(p, cols=cols)
        names.append(p.name)
        vecs.append(v)

    n = len(vecs)

    # Hamming & Cosine similarity matrices
    ham_mat: List[List[float]] = [[0.0] * n for _ in range(n)]
    cos_mat: List[List[float]] = [[0.0] * n for _ in range(n)]

    for i in range(n):
        ham_mat[i][i] = 1.0
        cos_mat[i][i] = 1.0
        for j in range(i + 1, n):
            h = hamming_similarity(vecs[i], vecs[j])
            c = cosine_similarity(vecs[i], vecs[j])
            ham_mat[i][j] = ham_mat[j][i] = h
            cos_mat[i][j] = cos_mat[j][i] = c

    print_similarity_matrix(names, ham_mat, "Hamming similarity matrix (1.000 = identical)")
    print_similarity_matrix(names, cos_mat, "Cosine similarity matrix (1.000 = identical)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Compute all-pairs similarity matrices for 2-bar drum patterns "
                    "(12-slot x cols binary grid, CH10 only)."
    )
    ap.add_argument('patterns', nargs='+',
                    help='MIDI pattern files to compare (e.g., RCK_P001.MID RCK_P002.MID).')
    ap.add_argument('--cols', type=int, default=32,
                    help='Number of time columns per 2-bar pattern (default: 32).')
    ap.add_argument('--version', action='version', version='adc-drum-sim-matrix 1.0')
    args = ap.parse_args()

    expanded: list[str] = []
    for pat in args.patterns:
        if any(ch in pat for ch in ('*', '?', '[')):
            matches = glob.glob(pat)
            expanded.extend(matches if matches else [pat])
        else:
            expanded.append(pat)

    paths = [Path(p) for p in expanded]
    compute_and_print_matrices(paths, cols=args.cols)


if __name__ == '__main__':
    main()
