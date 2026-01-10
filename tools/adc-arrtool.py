#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-arrtool.py
Convert APS ARR files to MIDI (Type 0) and/or ADS (simple event stream).

Defaults:
  - patterns dir: ./patterns (if missing, fall back to <ARR dir>/patterns if present)
  - velocity map: 0,40,80,110  (ADT levels 0..3 -> MIDI velocity)
"""

from __future__ import annotations

import argparse
import os
import re
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import mido
except ImportError:
    mido = None


# Some Web MIDI players may miss events scheduled exactly at tick 0.
# We start the generated count-in 1 tick late to avoid dropping the first hit.
COUNTIN_START_OFFSET_TICKS = 1


# ----------------------------
# ARR parsing
# ----------------------------

@dataclass
class ArrFile:
    bpm: int = 120
    mapping: Dict[int, str] = None
    main: List[int] = None
    countin_name: Optional[str] = None


def parse_arr(path: Path) -> ArrFile:
    """
    Parse a minimal subset of APS ARR that is sufficient for conversion:
      - BPM=...
      - N=FILENAME.ADT
      - MAIN|1,2,3,...
      - optional #COUNTIN name
    """
    bpm = 120
    mapping: Dict[int, str] = {}
    main: List[int] = []
    countin_name: Optional[str] = None

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        if line.startswith("#COUNTIN"):
            # e.g. "#COUNTIN CountIn_HH"
            parts = line.split(maxsplit=1)
            if len(parts) == 2:
                countin_name = parts[1].strip()
            continue

        if line.startswith("#"):
            continue

        if line.upper().startswith("BPM="):
            try:
                bpm = int(line.split("=", 1)[1].strip())
            except Exception:
                pass
            continue

        # mapping: "1=RCK_P001.ADT"
        m = re.match(r"^(\d+)\s*=\s*(.+)$", line)
        if m:
            idx = int(m.group(1))
            fname = m.group(2).strip()
            mapping[idx] = fname
            continue

        # main chain: "MAIN|1,2,3"
        if line.upper().startswith("MAIN|"):
            rhs = line.split("|", 1)[1].strip()
            if rhs:
                parts = [p.strip() for p in rhs.split(",") if p.strip()]
                for p in parts:
                    try:
                        main.append(int(p))
                    except Exception:
                        raise ValueError(f"Invalid MAIN entry: {p!r}")
            continue

    if not main:
        raise ValueError("ARR has no MAIN|... chain. MAIN is required.")
    if not mapping:
        raise ValueError("ARR has no pattern mapping lines like '1=XXXX.ADT'.")

    return ArrFile(bpm=bpm, mapping=mapping, main=main, countin_name=countin_name)


# ----------------------------
# ADT parsing (v2.2a-like)
# ----------------------------

@dataclass
class AdtPattern:
    name: str
    length: int                 # steps in the full grid file (often 32 for 2 bars)
    play_bars: int              # 1 or 2 (or more), used for chaining time
    slots: int
    slot_notes: List[int]       # MIDI note per slot index
    grid_levels: List[List[int]]  # [step][slot] 0..3
    grid_type: str = "16"


def _infer_play_bars_from_filename(stem: str) -> Optional[int]:
    # Convention in this project: "_h###" or "_H###" indicates half (1-bar) usage.
    # Examples: RCK_h901, END_h007
    if re.search(r"_[hH]\d{3}$", stem):
        return 1
    return None


def parse_adt(path: Path) -> AdtPattern:
    """
    Parse ADT text (APS/ADT v2.2a-style). Robust to the absence of a blank line
    between header and grid.

    Header keys:
      NAME=...
      GRID=...
      LENGTH=...
      SLOTS=...
      PLAY_BARS=... (optional)
      SLOTn=ABBR@NOTE,NAME  (NOTE is the MIDI note number)
    Grid:
      lines of symbols using . - x o (case-insensitive)
    """
    text = path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()

    header: Dict[str, str] = {}
    slot_notes: Dict[int, int] = {}
    grid_lines: List[str] = []

    in_grid = False
    for raw in lines:
        line = raw.rstrip("\n")
        s = line.strip()

        if not s:
            # Empty lines may exist; ignore them
            continue

        if not in_grid:
            # Header region
            if s.startswith(";"):
                continue

            if "=" in s:
                k, v = s.split("=", 1)
                header[k.strip().upper()] = v.strip()
                continue

            # First non-empty, non-comment line without '=' is treated as the first grid row
            in_grid = True
            grid_lines.append(s)
            continue

        # Grid region
        grid_lines.append(s)

    # ---- Interpret header ----
    name = header.get("NAME") or path.stem
    grid_type = header.get("GRID", "16")

    try:
        length = int(header.get("LENGTH", "32"))
    except Exception:
        length = 32

    try:
        slots = int(header.get("SLOTS", "12"))
    except Exception:
        slots = 12

    # PLAY_BARS (optional)
    play_bars: Optional[int] = None
    if "PLAY_BARS" in header:
        try:
            play_bars = int(header["PLAY_BARS"])
        except Exception:
            play_bars = None
    if play_bars is None:
        play_bars = _infer_play_bars_from_filename(path.stem) or 2

    # Slot notes from SLOTn lines (look for "@<note>")
    for k, v in header.items():
        if not k.startswith("SLOT"):
            continue
        m = re.match(r"^SLOT(\d+)$", k)
        if not m:
            continue
        idx = int(m.group(1))
        mm = re.search(r"@(\d+)", v)
        if mm:
            slot_notes[idx] = int(mm.group(1))

    notes = [slot_notes.get(i, 0) for i in range(slots)]    # Grid levels
    sym_map = {".": 0, "-": 1, "x": 2, "o": 3, "X": 2, "O": 3}
    grid_levels: List[List[int]] = []

    orientation = header.get("ORIENTATION", "STEP").strip().upper()

    def ch_to_lvl(ch: str) -> int:
        return sym_map.get(ch, 0)

    if orientation in ("LANE", "SLOT", "TRACK"):
        # grid_lines are lanes (one line per slot), each line length ~= LENGTH
        # Convert to step-major [step][slot]
        for step in range(length):
            row: List[int] = []
            for slot in range(slots):
                line = grid_lines[slot] if slot < len(grid_lines) else ""
                ch = line[step] if step < len(line) else "."
                row.append(ch_to_lvl(ch))
            grid_levels.append(row)
    else:
        # Default: STEP orientation (one line per step), each line length ~= SLOTS
        # If the file *looks* like LANE (len(grid_lines)==slots and lines are long), auto-detect.
        looks_like_lane = (len(grid_lines) == slots and any(len(gl) > slots for gl in grid_lines))
        if looks_like_lane:
            for step in range(length):
                row: List[int] = []
                for slot in range(slots):
                    line = grid_lines[slot] if slot < len(grid_lines) else ""
                    ch = line[step] if step < len(line) else "."
                    row.append(ch_to_lvl(ch))
                grid_levels.append(row)
        else:
            for i in range(min(length, len(grid_lines))):
                row_s = grid_lines[i]
                row: List[int] = []
                for j in range(slots):
                    ch = row_s[j] if j < len(row_s) else "."
                    row.append(ch_to_lvl(ch))
                grid_levels.append(row)

    while len(grid_levels) < length:
        grid_levels.append([0] * slots)

    return AdtPattern(
        name=name,
        length=length,
        play_bars=play_bars,
        slots=slots,
        slot_notes=notes,
        grid_levels=grid_levels,
        grid_type=grid_type,
    )


def build_countin_events(ppq: int, hihat_note: int = 42, velocity: int = 80,
                         gate_ratio: float = 0.5, time_sig_n: int = 4, time_sig_d: int = 4) -> Tuple[List[Tuple[int, str, int, int]], int]:
    """
    Build a 1-bar count-in: closed hi-hat hit once per beat (4 hits in 4/4).
    Returns (events, duration_ticks).
    """
    ticks_per_beat = int(ppq)
    ticks_per_bar = int(round(ticks_per_beat * time_sig_n * (4 / time_sig_d)))
    gate_ticks = max(1, int(ticks_per_beat * gate_ratio * 0.5))  # shorter than a beat

    events: List[Tuple[int, str, int, int]] = []
    for b in range(time_sig_n):
        t = COUNTIN_START_OFFSET_TICKS + b * ticks_per_beat  # start slightly after tick 0
        events.append((t, "on", int(hihat_note), int(velocity)))
        events.append((t + gate_ticks, "off", int(hihat_note), 0))

    events.sort(key=lambda x: (x[0], 0 if x[1] == "off" else 1, x[2]))
    return events, ticks_per_bar

# ----------------------------
# Conversion helpers
# ----------------------------


def resolve_countin_path(patterns_dir: Path, countin_name: str) -> Path:
    """
    Resolve count-in pattern reference to an actual .ADT file path.
    The ARR may store a bare name like 'CountIn_HH' (no extension).
    """
    name = countin_name.strip()
    if not name:
        return patterns_dir / "__MISSING__.ADT"
    if name.lower().endswith(".adt"):
        return patterns_dir / name
    return patterns_dir / (name + ".ADT")

def resolve_patterns_dir(arr_path: Path, patterns_dir_arg: Optional[str]) -> Path:
    if patterns_dir_arg:
        return Path(patterns_dir_arg)
    # default: ./patterns
    p1 = Path("patterns")
    if p1.is_dir():
        return p1
    # fallback: <ARR dir>/patterns
    p2 = arr_path.parent / "patterns"
    if p2.is_dir():
        return p2
    # as a last resort, still use ./patterns
    return p1


def build_timeline_events(
    patterns: List[AdtPattern],
    velocity_map: List[int],
    ppq: int,
    drum_channel: int = 9,
    gate_ratio: float = 0.5,
    time_sig_n: int = 4,
    time_sig_d: int = 4,
) -> List[Tuple[int, str, int, int]]:
    """
    Build a flat list of (abs_tick, kind, note, velocity).
    kind: "on" or "off".
    """
    events: List[Tuple[int, str, int, int]] = []

    ticks_per_beat = ppq
    # 16th note tick length for 4/4: PPQ / 4
    # We assume the ADT "step" corresponds to 1/16 if length=32 for 2 bars in 4/4.
    # More generally, we compute step_ticks from steps_per_bar:
    # ticks_per_bar = PPQ * beats_per_bar (e.g., 480*4=1920)
    ticks_per_bar = ticks_per_beat * time_sig_n * (4 / time_sig_d)

    cur_tick = 0

    for pat in patterns:
        play_bars = max(1, int(pat.play_bars))
        steps_total = int(pat.length)

        # Determine how many bars the *file grid* represents, independent of play_bars.
        # Half patterns often keep a 2-bar grid (length=32 or 24) but set play_bars=1.
        # If we naively divide by play_bars, a half pattern becomes '32 steps per bar' and sounds wrong.
        if steps_total in (32, 24):
            file_bars = 2
        elif steps_total in (16, 12):
            file_bars = 1
        else:
            # best-effort heuristic
            file_bars = 2 if steps_total >= 24 else 1

        steps_per_bar = max(1, steps_total // file_bars)
        step_ticks = int(round(ticks_per_bar / steps_per_bar))
        gate_ticks = max(1, int(step_ticks * gate_ratio))

        # Play only the requested number of bars from the file grid
        steps_to_play = min(steps_total, steps_per_bar * play_bars)

        for s in range(steps_to_play):
            abs_t = cur_tick + s * step_ticks
            levels = pat.grid_levels[s]
            for slot_idx, lvl in enumerate(levels):
                if lvl <= 0:
                    continue
                note = int(pat.slot_notes[slot_idx])
                if note <= 0:
                    continue
                vel = int(velocity_map[min(3, max(0, lvl))])
                # note_on
                events.append((abs_t, "on", note, vel))
                # note_off
                events.append((abs_t + gate_ticks, "off", note, 0))

        # advance time by played bars
        cur_tick += int(play_bars * ticks_per_bar)

    # Sort by abs tick, with note_off before note_on at same tick to avoid stuck notes
    events.sort(key=lambda x: (x[0], 0 if x[1] == "off" else 1, x[2]))
    return events


def write_midi_type0(
    out_path: Path,
    bpm: int,
    events: List[Tuple[int, str, int, int]],
    ppq: int,
    drum_channel: int = 9,
):
    if mido is None:
        raise RuntimeError("mido is not installed. Install it: pip install mido")

    mid = mido.MidiFile(type=0, ticks_per_beat=ppq)
    track = mido.MidiTrack()
    mid.tracks.append(track)

    # tempo meta
    tempo = mido.bpm2tempo(bpm)
    track.append(mido.MetaMessage("set_tempo", tempo=tempo, time=0))

    last_tick = 0
    for abs_t, kind, note, vel in events:
        dt = abs_t - last_tick
        last_tick = abs_t
        if kind == "on":
            track.append(mido.Message("note_on", channel=drum_channel, note=note, velocity=vel, time=dt))
        else:
            track.append(mido.Message("note_off", channel=drum_channel, note=note, velocity=0, time=dt))

    # end of track
    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(str(out_path))


def write_ads_simple(
    out_path: Path,
    bpm: int,
    ppq: int,
    events: List[Tuple[int, str, int, int]],
    drum_channel: int = 9,
):
    """
    Write a simple binary event stream. This is intentionally minimal and self-describing.

    Format (little-endian):
      0: 4 bytes  magic "ADS0"
      4: u16      version = 0x0001
      6: u16      bpm
      8: u16      ppq
      10:u8       channel (0..15)
      11:u8       reserved
      12:u32      event_count
      16: events...
          each event:
            u32 delta_ticks
            u8  kind (1=on, 0=off)
            u8  note
            u8  velocity (0 for off)
            u8  reserved
    """
    # Convert abs -> delta
    deltas: List[Tuple[int, int, int, int]] = []
    last = 0
    for abs_t, kind, note, vel in events:
        delta = abs_t - last
        last = abs_t
        k = 1 if kind == "on" else 0
        deltas.append((delta, k, note, vel))

    with open(out_path, "wb") as f:
        f.write(b"ADS0")
        f.write(struct.pack("<H", 0x0001))
        f.write(struct.pack("<H", int(bpm) & 0xFFFF))
        f.write(struct.pack("<H", int(ppq) & 0xFFFF))
        f.write(struct.pack("<B", int(drum_channel) & 0x0F))
        f.write(struct.pack("<B", 0))
        f.write(struct.pack("<I", len(deltas)))

        for delta, k, note, vel in deltas:
            f.write(struct.pack("<I", int(delta) & 0xFFFFFFFF))
            f.write(struct.pack("<B", k & 0xFF))
            f.write(struct.pack("<B", int(note) & 0xFF))
            f.write(struct.pack("<B", int(vel) & 0xFF))
            f.write(struct.pack("<B", 0))


# ----------------------------
# CLI
# ----------------------------

def parse_velocity_map(s: str) -> List[int]:
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("velocity map must have 4 comma-separated integers, e.g. 0,40,80,110")
    vals = []
    for p in parts:
        try:
            v = int(p)
        except Exception:
            raise argparse.ArgumentTypeError(f"invalid integer in velocity map: {p!r}")
        if v < 0 or v > 127:
            raise argparse.ArgumentTypeError("velocity values must be 0..127")
        vals.append(v)
    return vals


def main():
    ap = argparse.ArgumentParser(
        prog="adc-arrtool.py",
        description="Convert APS ARR to MIDI Type 0 and/or ADS (simple stream). MAIN chain is required.",
    )
    ap.add_argument("arr", help="Input .ARR file path")
    ap.add_argument("--format", choices=["midi", "ads", "both"], default="midi",
                    help="Output format (default: midi)")
    ap.add_argument("--out", default=None,
                    help="Output file path or output directory (default: beside ARR)")
    ap.add_argument("--patterns-dir", default=None,
                    help="ADT patterns directory (default: ./patterns, fallback: <ARR dir>/patterns)")
    ap.add_argument("--bpm", type=int, default=None,
                    help="Override BPM (default: use BPM from ARR)")
    ap.add_argument("--ppq", type=int, default=480,
                    help="MIDI ticks per beat (default: 480)")
    ap.add_argument("--velocity-map", type=parse_velocity_map, default=[0, 40, 80, 110],
                    help="ADT level(0..3)->MIDI velocity, e.g. 0,40,80,110")
    ap.add_argument("--drum-ch", type=int, default=10,
                    help="MIDI drum channel 1..16 (default: 10)")
    ap.add_argument("--gate", type=float, default=0.5,
                    help="Note gate ratio within a step (default: 0.5)")
    ap.add_argument("--with-countin", dest="with_countin", action="store_true",
                    help="Include ARR #COUNTIN pattern at the beginning (default)")
    ap.add_argument("--no-countin", dest="with_countin", action="store_false",
                    help="Do not include ARR #COUNTIN pattern")
    ap.set_defaults(with_countin=True)
    ap.add_argument("--countin", default=None,
                    help="Override count-in pattern (name or .ADT filename). Overrides ARR #COUNTIN")
    ap.add_argument("--strict", action="store_true",
                    help="Fail if any referenced pattern file is missing")
    args = ap.parse_args()

    arr_path = Path(args.arr)
    if not arr_path.is_file():
        raise SystemExit(f"[ERROR] ARR not found: {arr_path}")

    arr = parse_arr(arr_path)
    bpm = int(args.bpm) if args.bpm is not None else int(arr.bpm)

    patterns_dir = resolve_patterns_dir(arr_path, args.patterns_dir)

    # Expand MAIN indices -> pattern filenames
    expanded_files: List[Path] = []
    missing: List[str] = []

    # Optional count-in (generated): 1 bar, closed hi-hat once per beat.
    # In this workflow the count-in does not require an ADT file.
    countin_events: List[Tuple[int, str, int, int]] = []
    countin_ticks = 0
    if args.with_countin and (arr.countin_name or args.countin is not None):
        countin_vel = int(args.velocity_map[2]) if args.velocity_map else 80
        countin_events, countin_ticks = build_countin_events(
            ppq=int(args.ppq),
            hihat_note=42,
            velocity=countin_vel,
            gate_ratio=float(args.gate),
        )
    for idx in arr.main:
        if idx not in arr.mapping:
            missing.append(f"(missing mapping) {idx}")
            continue
        fname = arr.mapping[idx]
        p = patterns_dir / fname
        if not p.is_file():
            missing.append(str(p))
        expanded_files.append(p)

    if missing:
        msg = "[WARN] Missing patterns:\n  " + "\n  ".join(missing)
        if args.strict:
            raise SystemExit(msg)
        else:
            print(msg)

    # Load patterns
    patterns: List[AdtPattern] = []
    for p in expanded_files:
        if not p.is_file():
            # lenient: skip
            continue
        try:
            patterns.append(parse_adt(p))
        except Exception as e:
            if args.strict:
                raise
            print(f"[WARN] Failed to parse ADT {p.name}: {e}")

    if not patterns:
        raise SystemExit("[ERROR] No patterns loaded. Check --patterns-dir and ARR mapping.")

    drum_channel = int(args.drum_ch) - 1
    if drum_channel < 0 or drum_channel > 15:
        raise SystemExit("[ERROR] --drum-ch must be 1..16")

    events = build_timeline_events(
        patterns=patterns,
        velocity_map=args.velocity_map,
        ppq=int(args.ppq),
        
        gate_ratio=float(args.gate),
    )
    # Prepend generated count-in (if enabled)
    if countin_ticks > 0 and countin_events:
        shifted = [(t + countin_ticks, kind, note, vel) for (t, kind, note, vel) in events]
        events = countin_events + shifted


    # Output path handling
    stem = arr_path.stem
    out_arg = Path(args.out) if args.out else None

    def out_file(ext: str) -> Path:
        if out_arg is None:
            return arr_path.with_suffix(ext)
        if out_arg.suffix:
            # user gave a file path
            return out_arg
        # user gave a directory
        out_arg.mkdir(parents=True, exist_ok=True)
        return out_arg / (stem + ext)

    if args.format in ("midi", "both"):
        midi_path = out_file(".mid")
        write_midi_type0(midi_path, bpm=bpm, events=events, ppq=int(args.ppq), drum_channel=drum_channel)
        print(f"[OK] Wrote MIDI: {midi_path}")

    if args.format in ("ads", "both"):
        ads_path = out_file(".ads")
        write_ads_simple(ads_path, bpm=bpm, ppq=int(args.ppq), events=events, drum_channel=drum_channel)
        print(f"[OK] Wrote ADS:  {ads_path}")


if __name__ == "__main__":
    main()
