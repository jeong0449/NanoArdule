#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import argparse
import re
import struct

try:
    import mido
except Exception:
    mido = None


METATIME_NAME = "MetaTime"


@dataclass
class ArrFile:
    bpm: int
    mapping: Dict[int, str]
    main: List[int]
    bars: List[str]
    # count-in length in beats (TS denominator unit)
    #  0 : off
    # -1 : enabled but "default length" (1 bar = TS numerator beats)
    countin_beats: int


@dataclass
class AdtPattern:
    name: str
    path_stem: str
    grid: str
    length: int
    play_bars: int
    time_sig_n: int
    time_sig_d: int
    slots: int
    notes: List[int]
    grid_levels: List[List[int]]


Event = Tuple[int, str, int, int]  # (abs_tick, kind, a, b)


def grid_to_subdiv(grid: str) -> int:
    g = (grid or "16").strip().upper()
    if g == "8T":
        return 3
    if g == "16T":
        return 6
    return 4


def infer_play_bars_from_filename(stem: str) -> Optional[int]:
    if re.search(r"_[hH]\d{3}$", stem):
        return 1
    return None


def parse_time_sig(header: Dict[str, str]) -> Tuple[int, int]:
    if "TIME_SIG" in header:
        m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", header["TIME_SIG"])
        if m:
            n, d = int(m.group(1)), int(m.group(2))
            if n > 0 and d > 0:
                return n, d
    return 4, 4


def parse_velmap(s: Optional[str]) -> List[int]:
    if not s:
        return [0, 40, 80, 110]
    parts = [p.strip() for p in s.split(",")]
    if len(parts) != 4:
        raise ValueError('velmap must be "0,40,80,110" (4 ints)')
    out: List[int] = []
    for p in parts:
        v = int(p)
        if v < 0 or v > 127:
            raise ValueError("velmap values must be 0..127")
        out.append(v)
    return out


def velocity_from_level(level: int, velmap: List[int]) -> int:
    lvl = max(0, min(3, int(level)))
    return int(velmap[lvl])


def ticks_per_beat_from_ts(ppq: int, den: int) -> int:
    # Beat is defined as the TS denominator note.
    return max(1, int(round(ppq * (4.0 / float(den)))))



def parse_arr(path: Path) -> ArrFile:
    bpm = 120
    mapping: Dict[int, str] = {}
    main: List[int] = []
    bars: List[str] = []
    countin_beats = 0

    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        s = raw.strip()
        if not s:
            continue

        # ARR meta: #COUNTIN ...
        # Accept:
        #   #COUNTIN CountIn_HH
        #   #COUNTIN CountIn_HH 4
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in lines:
        s = raw.strip()
        if not s:
            continue

        # ARR meta: #COUNTIN ...
        # Accept:
        #   #COUNTIN CountIn_HH
        #   #COUNTIN CountIn_HH 4
        #   #COUNTIN 4
        m_ci = re.match(r"^\s*#COUNTIN(?:\s+(\S+))?(?:\s+(\d+))?\s*$", s, flags=re.IGNORECASE)
        if m_ci:
            if m_ci.group(2) is not None:
                countin_beats = max(0, int(m_ci.group(2)))
            else:
                countin_beats = -1  # enabled; default length decided later from TS
            continue

        # other comments
        if s.startswith("#"):
            continue

        u = s.upper()
        if u.startswith("BPM="):
            try:
                bpm = int(s.split("=", 1)[1].strip())
            except Exception:
                pass
            continue

        if u.startswith("MAIN|"):
            rhs = s.split("|", 1)[1].strip()
            for part in rhs.split(","):
                part = part.strip()
                if part:
                    # Note: adc-arrtool expects MAIN| already expanded (no xN syntax here).
                    main.append(int(part))
            continue

        if u.startswith("BARS|"):
            rhs = s.split("|", 1)[1].strip()
            toks = [t.strip().upper()[:1] for t in rhs.split(",") if t.strip()]
            bars = [t if t in ("F", "A", "B") else "F" for t in toks]
            continue

        # mapping: "1=RCK_P001.ADT"
        if "=" in s:
            k, v = s.split("=", 1)
            try:
                idx = int(k.strip())
            except Exception:
                continue
            mapping[idx] = v.strip().strip('"')

    if not main:
        raise ValueError("ARR has no MAIN| chain.")
    if not bars:
        bars = ["F"] * len(main)
    else:
        # Pad/truncate for safety (backward/forward compatibility).
        if len(bars) < len(main):
            bars = bars + ["F"] * (len(main) - len(bars))
        elif len(bars) > len(main):
            bars = bars[: len(main)]

    return ArrFile(bpm=bpm, mapping=mapping, main=main, bars=bars, countin_beats=countin_beats)


def parse_adt(path: Path) -> AdtPattern:
    header: Dict[str, str] = {}
    grid_lines: List[str] = []

    in_grid = False
    seen_header = False

    raw_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    for raw in raw_lines:
        s = raw.rstrip("\r\n")

        if not in_grid and not s.strip():
            continue
        if not in_grid and not seen_header and s.lstrip().startswith(";"):
            continue

        if not in_grid:
            if "=" in s:
                k, v = s.split("=", 1)
                header[k.strip().upper()] = v.strip()
                seen_header = True
                continue
            if seen_header and s.strip():
                in_grid = True

        if in_grid and s.strip():
            grid_lines.append(s.rstrip())

    name = header.get("NAME", path.stem)
    grid = header.get("GRID", "16").strip()
    time_sig_n, time_sig_d = parse_time_sig(header)

    try:
        length = int(header.get("LENGTH", "32").strip())
    except Exception:
        length = 32

    try:
        slots = int(header.get("SLOTS", "12").strip())
    except Exception:
        slots = 12

    play_bars: Optional[int] = None
    if "PLAY_BARS" in header:
        try:
            play_bars = int(header["PLAY_BARS"].strip())
        except Exception:
            play_bars = None
    if play_bars is None:
        play_bars = infer_play_bars_from_filename(path.stem) or 2

    # SLOT parsing: extract @NN anywhere (supports "KK@36,KICK")
    slot_pairs: List[Tuple[int, int]] = []
    for k, v in header.items():
        if not k.startswith("SLOT"):
            continue
        m = re.match(r"^SLOT(\d+)$", k)
        if not m:
            continue
        idx = int(m.group(1))
        mm = re.search(r"@(\d+)", v)
        note = int(mm.group(1)) if mm else 0
        slot_pairs.append((idx, note))

    if slot_pairs:
        max_idx = max(i for (i, _) in slot_pairs)
        if max_idx + 1 > slots:
            slots = max_idx + 1

    notes = [0] * slots
    for idx, note in slot_pairs:
        if 0 <= idx < len(notes):
            notes[idx] = note

    max_row_len = max((len(r) for r in grid_lines), default=0)
    if max_row_len > slots:
        notes.extend([0] * (max_row_len - slots))
        slots = max_row_len

    def ch_to_lvl(ch: str) -> int:
        c = (ch or ".").strip().lower()[:1]
        return {".": 0, "-": 1, "x": 2, "o": 3}.get(c, 0)

    grid_levels: List[List[int]] = []
    for row in grid_lines[:length]:
        row2 = row.ljust(slots, ".")[:slots]
        grid_levels.append([ch_to_lvl(c) for c in row2])

    while len(grid_levels) < length:
        grid_levels.append([0] * slots)

    return AdtPattern(
        name=name,
        path_stem=path.stem,
        grid=grid,
        length=length,
        play_bars=int(play_bars),
        time_sig_n=int(time_sig_n),
        time_sig_d=int(time_sig_d),
        slots=int(slots),
        notes=notes,
        grid_levels=grid_levels,
    )


def build_countin_events(ppq: int,
                         time_sig_n: int,
                         time_sig_d: int,
                         countin_beats: int,
                         start_tick_offset: int = 1,
                         hihat_note: int = 42,
                         velocity: int = 80,
                         gate_ratio: float = 0.5) -> Tuple[List[Event], int]:
    """
    Count-in by beats (not bars).
    Beat is TS denominator note.
    Tick=1 offset applies ONLY to count-in.
    """
    beats = max(0, int(countin_beats))
    if beats == 0:
        return [], 0

    tpb = ticks_per_beat_from_ts(ppq, time_sig_d)
    gate_ticks = max(1, int(round(tpb * gate_ratio)))
    length_ticks = beats * tpb

    events: List[Event] = []
    for i in range(beats):
        t = start_tick_offset + i * tpb
        events.append((t, "on", hihat_note, int(velocity)))
        events.append((t + gate_ticks, "off", hihat_note, 0))

    return events, length_ticks


def build_timeline_events(patterns: List[AdtPattern],
                          ppq: int,
                          velmap: List[int],
                          gate_ratio: float,
                          verbose: bool,
                          bars_list: Optional[List[str]] = None) -> List[Event]:

    events: List[Event] = []
    cur_tick = 0
    prev_ts: Optional[Tuple[int, int]] = None

    for i_p, p in enumerate(patterns):
        ts = (p.time_sig_n, p.time_sig_d)
        subdiv = grid_to_subdiv(p.grid)

        ticks_per_bar = int(round(ppq * ts[0] * (4.0 / ts[1])))
        steps_per_bar = max(1, ts[0] * subdiv)
        # Decide which bar to render for this chain entry.
        # - F: full (use p.play_bars)
        # - A: first bar only (cap to 1 bar)
        # - B: second bar only (cap to 1 bar; for 2-bar patterns, render bar2 shifted to start at 0)
        mode = "F"
        if bars_list is not None and 0 <= i_p < len(bars_list):
            m = str(bars_list[i_p] or "F").strip().upper()[:1]
            if m in ("F", "A", "B"):
                mode = m

        steps_to_play = max(1, steps_per_bar * int(p.play_bars))
        start_step = 0
        steps_render = min(steps_to_play, int(p.length))

        # Half patterns (PLAY_BARS=1) are always 1-bar, regardless of A/B.
        if int(p.play_bars) <= 1:
            start_step = 0
            steps_render = min(steps_per_bar, int(p.length))
            mode = mode  # semantic only
        else:
            if mode == "A":
                start_step = 0
                steps_render = min(steps_per_bar, int(p.length))
            elif mode == "B":
                start_step = min(steps_per_bar, max(0, int(p.length) - 1))
                steps_render = min(steps_per_bar, max(0, int(p.length) - start_step))
            else:
                start_step = 0
                steps_render = min(steps_to_play, int(p.length))
        step_ticks = max(1, int(round(ticks_per_bar / steps_per_bar)))
        gate_ticks = max(1, int(round(step_ticks * gate_ratio)))

        if prev_ts is None or prev_ts != ts:
            events.append((cur_tick, "meta_ts", ts[0], ts[1]))
            prev_ts = ts

        if verbose:
            print(
                f"[{METATIME_NAME}] PAT {p.path_stem} | TS={ts[0]}/{ts[1]} | GRID={p.grid} "
                f"(subdiv={subdiv}) | PLAY_BARS={p.play_bars} | "
                f"steps/bar={steps_per_bar} | steps(play)={steps_to_play} | "
                f"ticks/bar={ticks_per_bar} | step_ticks={step_ticks}"
            )

        # steps_render already computed above (after applying BARS selection)
        for s in range(steps_render):
            src_s = start_step + s
            base = cur_tick + s * step_ticks
            levels = p.grid_levels[src_s]
            limit = min(len(levels), len(p.notes))
            for i in range(limit):
                lvl = levels[i]
                note = p.notes[i]
                if lvl <= 0 or note <= 0:
                    continue
                vel = velocity_from_level(lvl, velmap)
                events.append((base, "on", note, vel))
                events.append((base + gate_ticks, "off", note, 0))

        # Advance timeline by the *played* duration (A/B -> 1 bar, F -> full).
        advance_steps = steps_to_play
        if int(p.play_bars) <= 1:
            advance_steps = steps_per_bar
        elif mode in ("A", "B"):
            advance_steps = steps_per_bar
        cur_tick += advance_steps * step_ticks

    order = {"meta_ts": 0, "on": 1, "off": 2}
    events.sort(key=lambda e: (e[0], order.get(e[1], 9)))
    return events


def write_midi_type0(out_path: Path,
                     bpm: int,
                     ppq: int,
                     drum_channel_1based: int,
                     events: List[Event]) -> None:
    if mido is None:
        raise RuntimeError("mido is required. Install: pip install mido")

    drum_ch = max(1, min(16, drum_channel_1based)) - 1
    mid = mido.MidiFile(type=0, ticks_per_beat=int(ppq))
    track = mido.MidiTrack()
    mid.tracks.append(track)

    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(int(bpm)), time=0))

    last_tick = 0
    for abs_t, kind, a, b in events:
        dt = int(abs_t - last_tick)
        if dt < 0:
            dt = 0
        last_tick = int(abs_t)

        if kind == "meta_ts":
            track.append(mido.MetaMessage(
                "time_signature",
                numerator=int(a),
                denominator=int(b),
                clocks_per_click=24,
                notated_32nd_notes_per_beat=8,
                time=dt
            ))
        elif kind == "on":
            track.append(mido.Message("note_on", channel=drum_ch, note=int(a), velocity=int(b), time=dt))
        elif kind == "off":
            track.append(mido.Message("note_off", channel=drum_ch, note=int(a), velocity=0, time=dt))

    track.append(mido.MetaMessage("end_of_track", time=0))
    mid.save(str(out_path))


def write_ads_simple(out_path: Path,
                     bpm: int,
                     ppq: int,
                     drum_channel_1based: int,
                     events: List[Event]) -> None:
    drum_ch = max(1, min(16, drum_channel_1based)) - 1
    note_events = [(t, k, a, b) for (t, k, a, b) in events if k in ("on", "off")]
    with out_path.open("wb") as f:
        f.write(struct.pack("<4sHHBI", b"ADS0", int(bpm), int(ppq), int(drum_ch) & 0xFF, len(note_events)))
        for abs_t, kind, note, vel in note_events:
            k = 1 if kind == "on" else 0
            f.write(struct.pack("<IBBBB", int(abs_t), k, int(note) & 0xFF, int(vel) & 0xFF, 0))


def main() -> None:
    ap = argparse.ArgumentParser(prog="adc-arrtool.py", add_help=True)
    ap.add_argument("arr", help="Input ARR file")
    ap.add_argument("--format", choices=["midi", "ads", "both"], default="midi",
                    help="Output format (default: midi)")
    ap.add_argument("--out", default=None,
                    help="Output file path (with suffix) or output directory. Default: beside ARR.\n"
                         "If --format both and --out is a file path, the suffix is replaced for .mid/.ads outputs.")
    ap.add_argument("--patterns-dir", default=None,
                    help="Directory containing ADT files referenced by ARR. Default: ARR directory.")
    ap.add_argument("--ppq", type=int, default=480, help="PPQ (ticks per quarter), default 480")
    ap.add_argument("--channel", type=int, default=10, help="Drum channel 1..16 (default 10)")
    ap.add_argument("--gate", type=float, default=0.5, help="Gate ratio relative to step length (default 0.5)")
    ap.add_argument("--velmap", default=None, help='Velocity map "0,40,80,110" for levels 0..3')

    # BPM override (restored)
    ap.add_argument("--bpm", type=int, default=None, help="Override BPM (default: use BPM from ARR)")

    # Count-in control:
    # - ARR: #COUNTIN ... enables count-in (default length: 1 bar = TS numerator beats)
    # - CLI: --countin N overrides (beats; 0 disables)
    # - legacy: --with-countin enables 1 bar unless --countin provided
    ap.add_argument("--countin", type=int, default=None,
                    help="Override count-in length in BEATS (TS denominator unit). 0 disables.")
    ap.add_argument("--with-countin", action="store_true",
                    help="Legacy: enable 1-bar count-in (TS numerator beats). Ignored if --countin is set.")

    ap.add_argument("--verbose", action="store_true", help="Print per-pattern MetaTime math")
    ap.add_argument("--quiet", action="store_true", help="Suppress MetaTime logs")
    ap.add_argument("--strict", action="store_true", help="Fail if any pattern is missing/unparseable")

    args = ap.parse_args()

    arr_path = Path(args.arr)
    if not arr_path.is_file():
        raise SystemExit(f"ARR not found: {arr_path}")

    patterns_dir = Path(args.patterns_dir) if args.patterns_dir else arr_path.parent
    if not patterns_dir.is_dir():
        raise SystemExit(f"patterns-dir not found: {patterns_dir}")

    arr = parse_arr(arr_path)

    bpm = int(args.bpm) if args.bpm is not None else int(arr.bpm)
    ppq = int(args.ppq)
    drum_ch_1based = int(args.channel)
    velmap = parse_velmap(args.velmap)

    # Resolve pattern paths from MAIN
    pattern_paths: List[Path] = []
    missing: List[str] = []
    for idx in arr.main:
        if idx not in arr.mapping:
            missing.append(f"(mapping missing) {idx}")
            continue
        p = patterns_dir / arr.mapping[idx]
        if not p.is_file():
            missing.append(str(p))
        pattern_paths.append(p)

    if missing:
        msg = "[WARN] Missing patterns:\n  " + "\n  ".join(missing)
        if args.strict:
            raise SystemExit(msg)
        if not args.quiet:
            print(msg)

    patterns: List[AdtPattern] = []
    for p in pattern_paths:
        if not p.is_file():
            continue
        try:
            patterns.append(parse_adt(p))
        except Exception as e:
            if args.strict:
                raise
            if not args.quiet:
                print(f"[WARN] Failed to parse {p.name}: {e}")

    if not patterns:
        raise SystemExit("No patterns could be loaded from MAIN chain.")

    if not args.quiet:
        print(f"[{METATIME_NAME}] ARR: {arr_path.name} | BPM={bpm} | PPQ={ppq} | DrumCH={drum_ch_1based}")
        print(f"[{METATIME_NAME}] Chain entries: {len(arr.main)} | Patterns loaded: {len(patterns)} | "
              f"Total PLAY_BARS: {sum((1 if (getattr(arr, 'bars', None) and i < len(arr.bars) and str(arr.bars[i]).upper()[:1] in ('A','B') and int(patterns[i].play_bars) >= 2) else int(patterns[i].play_bars)) for i in range(len(patterns)))}")

    # Decide count-in beats:
    # Priority: --countin > (legacy --with-countin) > ARR #COUNTIN > default 0
    if args.countin is not None:
        countin_beats = max(0, int(args.countin))
        countin_source = "CLI(--countin)"
    elif args.with_countin:
        countin_beats = int(patterns[0].time_sig_n)
        countin_source = "legacy(--with-countin)"
    else:
        if int(arr.countin_beats) < 0:
            countin_beats = int(patterns[0].time_sig_n)  # default 1 bar
        else:
            countin_beats = max(0, int(arr.countin_beats))
        countin_source = "ARR(#COUNTIN)"

    if not args.quiet:
        print(f"[{METATIME_NAME}] Count-in source: {countin_source} | beats={countin_beats}")

    countin_events: List[Event] = []
    countin_ticks = 0

    if countin_beats > 0:
        n0, d0 = patterns[0].time_sig_n, patterns[0].time_sig_d
        countin_events, countin_ticks = build_countin_events(
            ppq=ppq,
            time_sig_n=n0,
            time_sig_d=d0,
            countin_beats=countin_beats,
            start_tick_offset=1,
            hihat_note=42,
            velocity=int(velmap[2]),
            gate_ratio=float(args.gate),
        )
        if not args.quiet:
            print(f"[{METATIME_NAME}] Count-in: ON | TS={n0}/{d0} | beats={countin_beats} | start_tick=1 | length_ticks={countin_ticks}")
    else:
        if not args.quiet:
            print(f"[{METATIME_NAME}] Count-in: OFF")

    events = build_timeline_events(
        patterns=patterns,
        ppq=ppq,
        velmap=velmap,
        gate_ratio=float(args.gate),
        verbose=bool(args.verbose),
        bars_list=getattr(arr, 'bars', None),
    )

    # Shift main timeline after count-in
    if countin_events and countin_ticks > 0:
        shifted = [(t + countin_ticks, k, a, b) for (t, k, a, b) in events]
        events = countin_events + shifted
        order = {"meta_ts": 0, "on": 1, "off": 2}
        events.sort(key=lambda e: (e[0], order.get(e[1], 9)))

    total_events = len(events)
    note_events = sum(1 for (_, k, _, _) in events if k in ("on", "off"))
    meta_events = total_events - note_events
    end_tick = max((t for (t, _, _, _) in events), default=0)
    if not args.quiet:
        print(f"[{METATIME_NAME}] Events: total={total_events} | note={note_events} | meta={meta_events} | end_tick={end_tick}")

    def out_file(ext: str) -> Path:
        """Resolve output path for a given extension.

        Rules:
        - If --out is omitted: write beside ARR using ARR stem.
        - If --out is a directory path (no suffix): create it and write inside it.
        - If --out is a file path (has suffix):
            * for single-format output: use it as-is
            * for --format both: treat it as a *base name* and replace suffix per ext
              (prevents accidental overwrite of .mid by .ads or vice versa).
        """
        if args.out is None:
            return arr_path.with_suffix(ext)

        out_arg = Path(args.out)

        # --out points to a file path
        if out_arg.suffix:
            if args.format == "both":
                return out_arg.with_suffix(ext)
            return out_arg

        # --out points to a directory
        out_arg.mkdir(parents=True, exist_ok=True)
        return out_arg / (arr_path.stem + ext)

    if args.format in ("midi", "both"):
        midi_path = out_file(".MID")
        write_midi_type0(
            out_path=midi_path,
            bpm=bpm,
            ppq=ppq,
            drum_channel_1based=drum_ch_1based,
            events=events,
        )
        if not args.quiet:
            print(f"[OK] Wrote MIDI: {midi_path}")

    if args.format in ("ads", "both"):
        ads_path = out_file(".ADS")
        write_ads_simple(
            out_path=ads_path,
            bpm=bpm,
            ppq=ppq,
            drum_channel_1based=drum_ch_1based,
            events=events,
        )
        if not args.quiet:
            print(f"[OK] Wrote ADS:  {ads_path}")


if __name__ == "__main__":
    main()