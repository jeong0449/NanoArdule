#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-mid2adt.py (ADT v2.2a, auto triplet detection)
- Convert a 2-bar drum MIDI file into ADT text format (Ardule)
- Default assumptions: 4/4, 2 bars, GM 12-slot layout
- GRID/LENGTH are auto-detected from drum timing (unless --no-auto-grid is used)
    * GRID=16  -> LENGTH=32  (4/4 straight 16th grid)
    * GRID=8T  -> LENGTH=24  (triplet feel; 8th-triplet grid)
    * GRID=16T -> LENGTH=48  (triplet feel; 16th-triplet grid)

Requirements:
  pip install mido
"""

import argparse, sys, os, pathlib
from mido import MidiFile

# --- v2.2a defaults ---
ADT_VERSION_STR = "ADT v2.2"
DEFAULT_GRID = "16"     # auto-grid 실패 시 fallback
DEFAULT_LENGTH = 32     # auto-grid 실패 시 fallback
DEFAULT_TIME_SIG = "4/4"
DEFAULT_KIT = "GM_STD"
DEFAULT_ORIENTATION = "STEP"
DEFAULT_SLOTS = 12
DEFAULT_PPQN_NOTE = 96  # (정보용: 내부 ADP용 권고치, 여기선 미사용)

# GRID → subdivisions per beat
GRID_SUBDIV = {
    "16": 4,   # 16분 = 4 subdivision per beat
    "8T": 3,   # 8분 트리플렛
    "16T": 6,  # 16분 트리플렛
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
    p = argparse.ArgumentParser(description="2-bar drum MIDI → ADT (v2.2a, auto triplet detection; velocity symbols . - X O)")
    p.add_argument("input", nargs="?", help="Input MIDI file path (.mid). Can be omitted when using --in-dir.")
    p.add_argument("--in-dir", type=str, default=None, help="Input folder (batch-convert .mid files inside).")
    p.add_argument("--out-dir", type=str, default=None, help="Output folder (default: same as input).")
    p.add_argument("--recursive", action="store_true", help="When using --in-dir, process subfolders recursively.")
    # GRID/LENGTH: 기본은 auto detection, --no-auto-grid 사용 시에만 강제 적용
    p.add_argument("--grid", type=str, choices=["16","8T","16T"], default=DEFAULT_GRID,
                   help="(With --no-auto-grid) Force grid: 16 / 8T / 16T.")
    p.add_argument("--length", type=int, choices=[24,32,48], default=DEFAULT_LENGTH,
                   help="(With --no-auto-grid) Force step length: 24 / 32 / 48.")
    p.add_argument("--no-auto-grid", action="store_true",
                   help="Disable auto GRID/LENGTH detection and use --grid/--length as-is.")
    p.add_argument("--time-sig", type=str, default=DEFAULT_TIME_SIG,
                   help="Display time signature (e.g., 4/4, 3/4, 12/8).")
    p.add_argument("--kit", type=str, default=DEFAULT_KIT, help="KIT hint (e.g., GM_STD).")
    p.add_argument("--orientation", type=str, choices=["STEP","SLOT"], default=DEFAULT_ORIENTATION,
                   help="ADT body orientation (STEP recommended).")
    p.add_argument("--channel", type=int, default=10,
                   help="Drum channel (1–16, default 10=GM drums). 0/negative not allowed.")
    p.add_argument("--vel-thresholds", type=str, default="64,96,112",
                   help="Velocity thresholds for accent levels (three values, e.g. '64,96,112').")
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing .ADT files.")
    return p.parse_args()

def acc_from_velocity(v, thresholds):
    # thresholds: [t1, t2, t3] (e.g., [64, 96, 112]); v<=0 means rest
    if v <= 0: return 0
    if v < thresholds[0]: return 1
    if v < thresholds[1]: return 2
    # t3 is an upper hint; the max accent level is 3
    return 3

def acc_to_char(a):
    # Velocity symbols (low -> high), case-insensitive by convention:
    #   0: '.' (rest)
    #   1: '-' (soft)
    #   2: 'X' (medium)
    #   3: 'O' (strong/accent)
    return ['.', '-', 'X', 'O'][a]

def quantize_step(abs_ticks, tpq, grid, length):
    """
    abs_ticks: 현재 메시지의 절대 tick
    tpq: ticks per quarter (MIDI header)
    grid: "16"/"8T"/"16T"
    length: 총 스텝 수 (24/32/48)
    """
    subdiv = GRID_SUBDIV[grid]
    ticks_per_step = tpq / subdiv
    if ticks_per_step <= 0:
        step = 0
    else:
        step = int(round(abs_ticks / ticks_per_step))
    # Clamp events outside the 2-bar pattern length
    if step < 0: step = 0
    if step > length - 1: step = length - 1
    return step

def collect_drum_events(mid: MidiFile, drum_channel_one_based: int):
    """
    Collect absolute tick positions of drum-channel note_on (vel>0) events for GRID detection.
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
    Analyze drum events to auto-detect GRID (16/8T/16T) and LENGTH (32/24/48).
    - Method: for each GRID candidate, quantize event ticks to that grid and compute
      the average relative error (err / ticks_per_step); choose the smallest.
    - If events are insufficient or tpq<=0, fall back to DEFAULT_GRID/DEFAULT_LENGTH.
    """
    tpq, times = collect_drum_events(mid, drum_channel_one_based)
    if tpq <= 0 or not times:
        return DEFAULT_GRID, DEFAULT_LENGTH

    # Normalize ticks by subtracting the earliest event (relative timing matters).
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
            # relative error per step
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
    drum_channel_one_based: 1~16 (GM 드럼은 10)
    grid/length: 이미 auto-detect 또는 수동으로 결정된 값
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
            # Some DAWs may insert messages without a channel field
            ch = getattr(msg, "channel", None)
            if ch is None or ch != ch_idx:
                continue
            note = getattr(msg, "note", None)
            if note is None or note not in NOTE2SLOT:
                continue
            vel = getattr(msg, "velocity", 0) if msg.type == "note_on" else 0
            if vel <= 0:  # Ignore note_off or note_on vel=0 (gate handled by the engine)
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
    grid_data: STEP-major (length x 12) accent-level grid
    If ORIENTATION=SLOT, rotate the grid for SLOT-major output
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

    # Slot declarations
    for idx,(note,abbr,name) in enumerate(GM12):
        lines.append(f"SLOT{idx}={abbr}@{note},{name}")

    # Body
    if orientation == "STEP":
        # length줄 × 12문자
        for s in range(length):
            row = ''.join(acc_to_char(grid_data[s][j]) for j in range(DEFAULT_SLOTS))
            lines.append(row)
    else:
        # SLOT-우선(12줄 × length문자) — 90도 회전하여 출력
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

    # Validate drum channel
    ch = args.channel
    if not (1 <= ch <= 16):
        return False, f"--channel must be 1..16 (got {ch})"

    # Velocity thresholds
    try:
        th = [int(x.strip()) for x in args.vel_thresholds.split(",")]
        if len(th) != 3:
            raise ValueError
        th.sort()  # 오름차순 보장
    except Exception:
        return False, f"--vel-thresholds must be like '64,96,112'"

    # Auto-detect GRID/LENGTH or use manual settings
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
        for p in root.glob("*.mid"):
            yield p
        for p in root.glob("*.MID"):
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

    # 단일 파일 모드
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
