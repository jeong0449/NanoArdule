#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-mid2adt.py — MIDI (drums) to ADT text converter (ADT v2.2a)

Overview
- Convert a 2-bar drum MIDI pattern into an ADT text file.
- Assumes 4/4, 2 bars, and the GM 12-slot drum mapping by default.
- Grid/step resolution is automatically detected by analyzing note-on timing:
  * GRID=16  -> LENGTH=32  (4/4 straight 16th grid)
  * GRID=8T  -> LENGTH=24  (8th-note triplet feel / 12 steps per bar)
  * GRID=16T -> LENGTH=48  (16th-note triplet grid)
- If needed, you can override detection with --no-auto-grid and force --grid/--length.

Requirement
- pip install mido
"""


import argparse, sys, os, pathlib
from mido import MidiFile

# NOTE: (translated) --- v2.2   ---
ADT_VERSION_STR = "ADT v2.2a"
DEFAULT_GRID = "16"     # Fallback if auto-grid detection fails
DEFAULT_LENGTH = 32     # Fallback if auto-grid detection fails
DEFAULT_TIME_SIG = "4/4"
DEFAULT_KIT = "GM_STD"
DEFAULT_ORIENTATION = "STEP"
DEFAULT_SLOTS = 12
DEFAULT_PPQN_NOTE = 96  # (Informational: recommended internal value for ADP; not used here)

# GRID -> subdivisions per beat
GRID_SUBDIV = {
    "16": 4,   # 16 = 4 subdivision per beat
    "8T": 3,   # 8th-note triplet
    "16T": 6,  # 16th-note triplet
}

GRID_LENGTH = {
    "16": 32,
    "8T": 24,
    "16T": 48,
}

# GM 12-slot preset: (note, abbr, name)
GM12 = [
    (36,"KK","KICK"), (38,"SN","SNARE"), (42,"CH","HH_CL"), (46,"OH","HH_OP"),
    (45,"LT","TOM_L"), (47,"MT","TOM_M"), (50,"HT","TOM_H"), (51,"RD","RIDE"),
    (49,"CR","CRASH"), (37,"RM","RIM"),  (39,"CL","CLAP"),  (44,"PH","HH_PED"),
]
NOTE2SLOT = {n:i for i,(n,_,_) in enumerate(GM12)}

def parse_args():
    p = argparse.ArgumentParser(description="2-bar MIDI (drums) → ADT (v2.2, auto triplet detection)")
    p.add_argument("input", nargs="?", help="Input MIDI file path (.mid). Optional when --in-dir is used")
    p.add_argument("--in-dir", type=str, default=None, help="Input folder (batch convert *.mid inside)")
    p.add_argument("--out-dir", type=str, default=None, help="Output folder (default: same as input)")
    p.add_argument("--recursive", action="store_true", help="When using --in-dir, process subfolders recursively")
    # GRID/LENGTH: Automatic detection is enabled by default, --no-auto-grid only when enabled force override
    p.add_argument("--grid", type=str, choices=["16","8T","16T"], default=DEFAULT_GRID,
                   help="Force grid type (16 / 8T / 16T); effective only with --no-auto-grid.")
    p.add_argument("--length", type=int, choices=[24,32,48], default=DEFAULT_LENGTH,
                   help="Force pattern length in steps (24 / 32 / 48); effective only with --no-auto-grid.")
    p.add_argument("--no-auto-grid", action="store_true",
                   help="Disable automatic grid detection and use --grid/--length as specified.")
    p.add_argument("--time-sig", type=str, default=DEFAULT_TIME_SIG,
                   help="Time signature to write into ADT metadata (e.g., 4/4).")
    p.add_argument("--kit", type=str, default=DEFAULT_KIT, help="Kit identifier to write into ADT metadata (free-form string).")
    p.add_argument("--orientation", type=str, choices=["STEP","SLOT"], default=DEFAULT_ORIENTATION,
                   help="Grid orientation in ADT text output: STEP or SLOT.")
    p.add_argument("--channel", type=int, default=10,
                   help="Drum channel to extract (1–16; default: 10).")
    p.add_argument("--vel-thresholds", type=str, default="64,96,112",
                   help="Velocity thresholds for mapping hits to '-', 'X', 'O' (comma-separated, e.g., 64,96,112).")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing output .ADT files (otherwise skip).")
    return p.parse_args()

def acc_from_velocity(v, thresholds):
# NOTE: (translated) thresholds: [t1,t2,t3] (: [64,96,112]); v<=0 rest
    if v <= 0: return 0
    if v < thresholds[0]: return 1
    if v < thresholds[1]: return 2
# NOTE: (translated) t3  ,  3
    return 3

def acc_to_char(a):
    return ['.','-', 'x','o'][a]

def quantize_step(abs_ticks, tpq, grid, length):
    """
    abs_ticks:    tick
    tpq: ticks per quarter (MIDI header)
    grid: "16"/"8T"/"16T"
    length:  number of steps (24/32/48)
    """
    subdiv = GRID_SUBDIV[grid]
    ticks_per_step = tpq / subdiv
    if ticks_per_step <= 0:
        step = 0
    else:
        step = int(round(abs_ticks / ticks_per_step))
# NOTE: (translated) 2( )
    if step < 0: step = 0
    if step > length - 1: step = length - 1
    return step

def collect_drum_events(mid: MidiFile, drum_channel_one_based: int):
    """
    ADT/GRID     note_on(vel>0)   tick  .
    """
    tpq = mid.ticks_per_beat
    ch_idx = drum_channel_one_based - 1  # 0~15
    times = []

    for tr in mid.tracks:
        abs_t = 0
        for msg in tr:
            abs_t += msg.time
            if not hasattr(msg, "type"):
                continue
            if msg.type != "note_on":
                continue
            ch = getattr(msg, "channel", None)
            if ch is None or ch != ch_idx:
                continue
            note = getattr(msg, "note", None)
            if note is None or note not in NOTE2SLOT:
                continue
            vel = getattr(msg, "velocity", 0)
            if vel <= 0:
                continue
            times.append(abs_t)

    return tpq, times

def detect_grid_and_length(mid: MidiFile, drum_channel_one_based: int):
    """
        GRID(16/8T/16T) LENGTH(32/24/48)  .
    - :  GRID   tick    step  quantize  
       ( tick_per_step   )    .
    - If events are insufficient or TPQ<=0, fall back to DEFAULT_GRID/DEFAULT_LENGTH.
    """
    tpq, times = collect_drum_events(mid, drum_channel_one_based)
    if tpq <= 0 or not times:
        return DEFAULT_GRID, DEFAULT_LENGTH

    # Align to the earliest event (relative timing matters more than absolute start).
    t0 = min(times)
    norm_times = [t - t0 for t in times]

    best_grid = None
    best_score = None

    for grid, subdiv in GRID_SUBDIV.items():
        ticks_per_step = tpq / subdiv
        if ticks_per_step <= 0:
            continue
        total_err = 0.0
        for t in norm_times:
            step = round(t / ticks_per_step)
            ideal = step * ticks_per_step
            err = abs(t - ideal)
            # Relative error in step units.
            total_err += err / ticks_per_step
        score = total_err / len(norm_times)
        if (best_score is None) or (score < best_score):
            best_score = score
            best_grid = grid

    if best_grid is None:
        return DEFAULT_GRID, DEFAULT_LENGTH

    length = GRID_LENGTH[best_grid]
    return best_grid, length

def extract_grid_from_midi(mid: MidiFile, drum_channel_one_based: int, grid: str, length: int,
                           thresholds):
    """
    mid: mido.MidiFile
    drum_channel_one_based: 1–16 (GM drums use 10).
    grid/length: already decided by auto-detect or manual override.
    """
    tpq = mid.ticks_per_beat
    ch_idx = drum_channel_one_based - 1  # 0~15
    grid_data = [[0]*DEFAULT_SLOTS for _ in range(length)]

    for tr in mid.tracks:
        abs_t = 0
        for msg in tr:
            abs_t += msg.time
            if not hasattr(msg, "type"): 
                continue
            if msg.type not in ("note_on","note_off"):
                continue
            # Some DAWs may emit meta messages without a channel field.
            ch = getattr(msg, "channel", None)
            if ch is None or ch != ch_idx:
                continue
            note = getattr(msg, "note", None)
            if note is None or note not in NOTE2SLOT:
                continue
            vel = getattr(msg, "velocity", 0) if msg.type == "note_on" else 0
            if vel <= 0:  # Ignore note_off or vel=0 (note gating is handled by the engine).
                continue

            step = quantize_step(abs_t, tpq, grid, length)
            slot = NOTE2SLOT[note]
            acc  = acc_from_velocity(vel, thresholds)
            if acc > grid_data[step][slot]:
                grid_data[step][slot] = acc

    return tpq, grid_data

def write_adt(path_out: pathlib.Path, name_base: str, grid: str, length: int,
              time_sig: str, kit: str, orientation: str, grid_data):
    """
    grid_data: STEP-major (length × 12) accent-level grid.
    If orientation is SLOT, rotate the grid by 90° for output.
    """
    lines = []
    lines.append(f"; {ADT_VERSION_STR}")
    lines.append(f"NAME={name_base}")
    lines.append(f"TIME_SIG={time_sig}")
    lines.append(f"GRID={grid}")
    lines.append(f"LENGTH={length}")
    lines.append(f"SLOTS={DEFAULT_SLOTS}")
    lines.append(f"KIT={kit}")
    lines.append(f"ORIENTATION={orientation}")

    # Slot header
    for idx,(note,abbr,name) in enumerate(GM12):
        lines.append(f"SLOT{idx}={abbr}@{note},{name}")

    # Body
    if orientation == "STEP":
        # length lines × 12 characters
        for s in range(length):
            row = ''.join(acc_to_char(grid_data[s][j]) for j in range(DEFAULT_SLOTS))
            lines.append(row)
    else:
        # SLOT-major (12 lines × length chars noting steps) — output as a 90° rotated view.
        for j in range(DEFAULT_SLOTS):
            row = ''.join(acc_to_char(grid_data[s][j]) for s in range(length))
            lines.append(row)

    text = "\n".join(lines) + "\n"
    path_out.write_text(text, encoding="utf-8")

def convert_file(path_in: pathlib.Path, out_dir: pathlib.Path, args):
    if not path_in.exists() or path_in.suffix.lower() not in [".mid", ".midi"]:
        return False, f"skip (not midi): {path_in}"

    name_base = path_in.stem
    path_out  = (out_dir / name_base).with_suffix(".ADT")

    if path_out.exists() and not args.overwrite:
        return False, f"exists: {path_out.name} (use --overwrite)"

    # Load MIDI
    try:
        mid = MidiFile(str(path_in))
    except Exception as e:
        return False, f"mido load error: {path_in.name}: {e}"

    # Channel check
    ch = args.channel
    if not (1 <= ch <= 16):
        return False, f"--channel must be 1..16 (got {ch})"

    # velocity thresholds
    try:
        th = [int(x.strip()) for x in args.vel_thresholds.split(",")]
        if len(th) != 3:
            raise ValueError
        th.sort()  # Ensure ascending order
    except Exception:
        return False, f"--vel-thresholds must be like '64,96,112'"

    # Auto-detect GRID/LENGTH or use manual override
    if args.no_auto_grid:
        grid = args.grid
        length = args.length
        auto_info = "manual"
    else:
        grid, length = detect_grid_and_length(mid, ch)
        auto_info = "auto"

    time_sig = args.time_sig
    kit      = args.kit
    orientation = args.orientation

    # Extract grid from MIDI
    tpq, grid_data = extract_grid_from_midi(mid, ch, grid, length, th)

    # Write output
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        write_adt(path_out, name_base, grid, length, time_sig, kit, orientation, grid_data)
    except Exception as e:
        return False, f"write error: {path_out.name}: {e}"

    return True, f"ok: {path_in.name} -> {path_out.name} (tpq={tpq}, grid={grid}, len={length}, {auto_info})"

def iter_midi_files(root: pathlib.Path, recursive: bool):
    if not recursive:
        # On Windows, glob patterns may match case-insensitively, so "*.mid" and "*.MID"
        # can yield the same files twice. De-duplicate by resolved absolute path.
        seen = set()
        for pat in ("*.mid", "*.MID"):
            for p in root.glob(pat):
                rp = p.resolve()
                if rp in seen:
                    continue
                seen.add(rp)
                yield p
    else:
        for p in root.rglob("*"):
            if p.suffix.lower() in (".mid",".midi"):
                yield p

def main():
    args = parse_args()

    if args.in_dir:
        in_root = pathlib.Path(args.in_dir)
        if not in_root.exists():
            print(f"[ERR] no such dir: {in_root}", file=sys.stderr); sys.exit(1)
        out_root = pathlib.Path(args.out_dir) if args.out_dir else in_root
        total = ok = 0
        for p in iter_midi_files(in_root, args.recursive):
            total += 1
            success, msg = convert_file(p, out_root, args)
            print(("[OK] " if success else "[SKIP] ") + msg)
            if success: ok += 1
        print(f"\nDone. {ok}/{total} converted.")
        sys.exit(0)

    # Single-file mode
    if not args.input:
        print("Usage: adc-mid2adt.py <file.mid> [--no-auto-grid --grid 16|8T|16T --length 24|32|48] ...", file=sys.stderr)
        sys.exit(1)

    path_in = pathlib.Path(args.input)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else path_in.parent
    success, msg = convert_file(path_in, out_dir, args)
    print(("[OK] " if success else "[ERR] ") + msg)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()