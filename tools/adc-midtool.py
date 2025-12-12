#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-midtool.py — Unified MIDI manager for the Ardule platform

This tool integrates the original `adc-miditool` and `adc-mid-check`
functionalities into a single CLI utility.

Main capabilities
-----------------
- Scan a directory for Standard MIDI Files (.mid)
- Parse SMF headers (format, track count, division)
- Optional deep analysis using `mido` (duration, channels, notes, etc.)
- Normalize filenames to DOS 8.3 UPPERCASE format
- Convert SMF Type 1 → Type 0 (in-place)
- Generate INDEX-style listing (e.g., INDEX.TXT)
- Validate GM drum range (Channel 10 notes must be 35–81)
- Export CSV / JSON summaries for further inspection
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import struct
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

# Optional deep parser (mido)
try:
    import mido
    from mido import MidiFile, MidiTrack, MetaMessage, merge_tracks
    HAVE_MIDO = True
except Exception:  # pragma: no cover - optional dependency
    HAVE_MIDO = False

MTHD = b"MThd"
EIGHT_THREE_BASE = re.compile(r"^[A-Za-z0-9_]{1,8}$")
EIGHT_THREE_EXT = re.compile(r"^[A-Za-z0-9]{1,3}$")

# GM Drum channel constraints (Channel 10 = MIDI channel 9, 0-based)
GM_DRUM_MIN = 35
GM_DRUM_MAX = 81


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def naturalsort_key(s: str):
    """Return a key for natural sorting (numbers in strings sorted numerically)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def is_8dot3(name: str) -> bool:
    """Return True if name looks like classic DOS 8.3.

    Rules:
      - basename: 1–8 chars, [A-Za-z0-9_]
      - extension: 1–3 chars, [A-Za-z0-9]
      - exactly one dot separating base and ext
    """
    name = os.path.basename(name).strip()
    base, dot, ext = name.partition(".")
    if not dot:
        return False
    if "." in ext:
        return False
    return bool(EIGHT_THREE_BASE.fullmatch(base)) and bool(EIGHT_THREE_EXT.fullmatch(ext))


def sanitize_base(name: str) -> str:
    """Sanitize arbitrary filename base into an 8.3-compatible root."""
    base = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if not base:
        base = "MID"
    return base.upper()


def propose_8dot3(name: str, existing_upper: set) -> str:
    """Return a unique 8.3 uppercase filename; extension is forced to .MID."""
    base = name.rsplit(".", 1)[0] if "." in name else name
    base = sanitize_base(base)[:8]
    ext = "MID"

    def cand(b: str, n: Optional[int] = None) -> str:
        if n is None:
            return f"{b}.{ext}"
        tail = f"~{n}"
        max_root = max(1, 8 - len(tail))
        b2 = (b[:max_root] + tail)[:8]
        return f"{b2}.{ext}"

    c = cand(base)
    if c.upper() not in existing_upper:
        return c

    for n in range(1, 1000):
        c = cand(base, n)
        if c.upper() not in existing_upper:
            return c

    for n in range(1000, 10000):
        c = cand("MID", n)
        if c.upper() not in existing_upper:
            return c

    return "UNTITLED.MID"


def safe_rename(src: str, dst: str) -> None:
    """Rename with case-insensitive safety (especially on Windows)."""
    if os.path.abspath(src) == os.path.abspath(dst):
        return
    if os.path.exists(dst):
        raise FileExistsError(dst)

    # Case-insensitive safety within same directory
    if (os.path.dirname(src) == os.path.dirname(dst) and
            os.path.basename(src).lower() == os.path.basename(dst).lower()):
        tmp = os.path.join(os.path.dirname(src), f".ren_{os.getpid()}.tmp")
        os.rename(src, tmp)
        os.rename(tmp, dst)
    else:
        os.rename(src, dst)


# ---------------------------------------------------------------------------
# MIDI parsing / analysis
# ---------------------------------------------------------------------------

def parse_smf_header(path: str) -> Dict[str, Any]:
    """Parse the SMF MThd header.

    Returns dict with 'format', 'ntrks', 'division'.
    Raises ValueError on invalid header.
    """
    with open(path, "rb") as f:
        head = f.read(14)

    if len(head) < 14 or head[:4] != MTHD:
        raise ValueError("Missing 'MThd' header")

    length = struct.unpack(">I", head[4:8])[0]
    if length != 6:
        raise ValueError(f"Unexpected MThd length={length}")

    fmt, ntrks, division = struct.unpack(">HHH", head[8:14])
    return {"format": fmt, "ntrks": ntrks, "division": division}


def deep_mido_info(path: str) -> Dict[str, Any]:
    """Return extended MIDI information (via mido) if available.

    Includes:
      - duration_sec
      - format_mido
      - tpqn (ticks_per_beat)
      - channels_used
      - gm_drum_bad_notes (out-of-range notes on channel 10)
    """
    out: Dict[str, Any] = {}
    if not HAVE_MIDO:
        return out

    try:
        mid = MidiFile(path)
    except Exception as e:  # pragma: no cover - I/O / parsing errors
        return {"mido_error": str(e)}

    out["duration_sec"] = round(getattr(mid, "length", 0.0), 3)
    out["format_mido"] = getattr(mid, "type", None)
    out["tpqn"] = getattr(mid, "ticks_per_beat", None)

    channels_used = set()
    out_range_notes = []

    for track in mid.tracks:
        for msg in track:
            t = getattr(msg, "type", "")
            if t == "note_on" and getattr(msg, "velocity", 0) > 0:
                ch = getattr(msg, "channel", None)
                note = getattr(msg, "note", None)
                if ch is not None:
                    channels_used.add(ch)
                    # GM drum check on channel 10 (0-based ch=9)
                    if ch == 9 and note is not None:
                        if not (GM_DRUM_MIN <= note <= GM_DRUM_MAX):
                            out_range_notes.append(note)
            elif t == "program_change":
                ch = getattr(msg, "channel", None)
                if ch is not None:
                    channels_used.add(ch)

    out["channels_used"] = sorted(channels_used)
    out["gm_drum_bad_notes"] = sorted(set(out_range_notes))
    return out


def convert_type1_to_type0(path: str) -> Tuple[bool, str]:
    """Convert SMF Type 1 → Type 0 in-place.

    Returns (changed, message).
    """
    if not HAVE_MIDO:
        return False, "mido not installed"
    try:
        mid = MidiFile(path)
    except Exception as e:  # pragma: no cover - parse failure
        return False, f"mido open failed: {e}"

    if getattr(mid, "type", 0) != 1:
        return False, "not type 1"

    try:
        merged = merge_tracks(mid.tracks)
        msgs = [m for m in merged if getattr(m, "type", "") != "end_of_track"]
        msgs.append(MetaMessage("end_of_track", time=0))

        out = MidiFile(type=0, ticks_per_beat=mid.ticks_per_beat)
        tr = MidiTrack()
        tr.extend(msgs)
        out.tracks.append(tr)

        fd, tmp = tempfile.mkstemp(prefix="mid_", suffix=".mid",
                                   dir=os.path.dirname(path) or ".")
        os.close(fd)
        out.save(tmp)
        os.replace(tmp, path)
        return True, "converted type 1 → type 0"
    except Exception as e:  # pragma: no cover - write failure
        return False, f"convert failed: {e}"


def scan_directory(path: str, deep: bool = True) -> List[Dict[str, Any]]:
    """Scan a directory for .mid files and collect analysis rows."""
    rows: List[Dict[str, Any]] = []
    for fn in sorted(os.listdir(path)):
        if not fn.lower().endswith(".mid"):
            continue

        full = os.path.join(path, fn)
        if not os.path.isfile(full):
            continue

        row: Dict[str, Any] = {
            "name": fn,
            "size_bytes": os.path.getsize(full),
            "mtime": dt.datetime.fromtimestamp(os.path.getmtime(full)).isoformat(timespec="seconds"),
            "is_8dot3": is_8dot3(fn),
        }

        try:
            hdr = parse_smf_header(full)
            row.update(hdr)
        except Exception as e:
            row.update({
                "format": None,
                "ntrks": None,
                "division": None,
                "header_error": str(e),
            })

        if deep:
            row.update(deep_mido_info(full))

        rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# INDEX / fix operations
# ---------------------------------------------------------------------------

def write_index(path: str,
                names: List[str],
                filename: str,
                uppercase: bool,
                natural: bool) -> str:
    """Write an INDEX-style listing of MIDI filenames."""
    if natural:
        names = sorted(names, key=naturalsort_key)
    else:
        names = sorted(names)

    if uppercase:
        names = [n.upper() for n in names]

    out_path = os.path.join(path, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        for n in names:
            f.write(n + "\n")
    return out_path


def apply_fixes(path: str,
                fix_names: bool,
                convert_type1_flag: bool,
                index_filename: Optional[str],
                index_all: bool,
                index_upper: bool,
                index_natural: bool) -> Tuple[List[Tuple[str, str]], List[str], Optional[str]]:
    """Apply requested fixes: rename, convert type, generate index."""
    entries = [fn for fn in os.listdir(path)
               if fn.lower().endswith(".mid") and os.path.isfile(os.path.join(path, fn))]
    existing_upper = {e.upper() for e in entries}

    renamed: List[Tuple[str, str]] = []
    converted: List[str] = []

    # Renaming + Type 1 → Type 0
    for fn in sorted(entries, key=naturalsort_key):
        full = os.path.join(path, fn)

        # Rename to 8.3 if requested
        if fix_names and not is_8dot3(fn):
            new = propose_8dot3(fn, existing_upper)
            if new.upper() != fn.upper():
                safe_rename(full, os.path.join(path, new))
                renamed.append((fn, new))
                existing_upper.discard(fn.upper())
                existing_upper.add(new.upper())
                fn = new
                full = os.path.join(path, new)

        # Convert Type 1 if requested
        if convert_type1_flag:
            try:
                fmt = parse_smf_header(full).get("format")
            except Exception:
                fmt = None
            if fmt == 1:
                changed, msg = convert_type1_to_type0(full)
                if changed:
                    converted.append(fn)
                else:
                    print(f"[WARN] {fn}: {msg}", file=sys.stderr)

    # INDEX generation
    idx_path: Optional[str] = None
    if index_filename:
        if index_all:
            names = [fn for fn in os.listdir(path)
                     if fn.lower().endswith(".mid") and os.path.isfile(os.path.join(path, fn))]
        else:
            # Index only files touched in this operation (renamed+converted)
            names = [b for (_a, b) in renamed]
            names.extend(converted)
            names = sorted(set(names), key=naturalsort_key)
        idx_path = write_index(path, names, index_filename, index_upper, index_natural)

    return renamed, converted, idx_path


# ---------------------------------------------------------------------------
# Printing / export helpers
# ---------------------------------------------------------------------------

def print_table(rows: List[Dict[str, Any]]) -> None:
    """Print a compact table summarizing the scanned MIDI files."""
    cols = [
        "name",
        "size_bytes",
        "format",
        "ntrks",
        "division",
        "duration_sec",
        "is_8dot3",
        "channels_used",
        "gm_drum_bad_notes",
    ]
    header = " | ".join(f"{c:>16}" for c in cols)
    print(header)
    print("-" * len(header))

    def fmt(v: Any) -> str:
        if isinstance(v, float):
            return f"{v:.3f}"
        return str(v)

    for r in rows:
        line = " | ".join(f"{fmt(r.get(c, ''))[:16]:>16}" for c in cols)
        print(line)


def export_csv(path: str, rows: List[Dict[str, Any]]) -> None:
    """Export analysis rows to CSV."""
    cols = [
        "name",
        "size_bytes",
        "format",
        "ntrks",
        "division",
        "duration_sec",
        "is_8dot3",
        "channels_used",
        "gm_drum_bad_notes",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            out_row: List[Any] = []
            for c in cols:
                v = r.get(c, "")
                if isinstance(v, list):
                    v = ",".join(map(str, v))
                out_row.append(v)
            w.writerow(out_row)
    print(f"[CSV] wrote: {path}")


def export_json(path: str, rows: List[Dict[str, Any]]) -> None:
    """Export analysis rows to JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)
    print(f"[JSON] wrote: {path}")


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------

def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="adc-midtool",
        description=(
            "adc-midtool — unified MIDI inspector / fixer / drum validator "
            "for the Ardule ecosystem."
        ),
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Directory to scan (default: current directory)",
    )
    parser.add_argument(
        "--csv",
        metavar="CSV_PATH",
        help="Export table summary to CSV",
    )
    parser.add_argument(
        "--json",
        metavar="JSON_PATH",
        help="Export full analysis rows to JSON",
    )
    parser.add_argument(
        "--no-deep",
        action="store_true",
        help="Disable deep analysis (no mido-based scan)",
    )
    parser.add_argument(
        "--fix-names",
        action="store_true",
        help="Rename filenames to DOS 8.3 UPPERCASE (e.g., RCK_P001.MID)",
    )
    parser.add_argument(
        "--convert-type1",
        action="store_true",
        help="Convert SMF Type 1 files to Type 0 in-place",
    )
    parser.add_argument(
        "--write-index",
        nargs="?",
        const="INDEX.TXT",
        metavar="FILENAME",
        help="Write an INDEX-style listing file (default: INDEX.TXT)",
    )
    parser.add_argument(
        "--index-all",
        action="store_true",
        help="When writing index, include all .mid files in the directory",
    )
    parser.add_argument(
        "--index-uppercase",
        action="store_true",
        help="Uppercase names in the index file",
    )
    parser.add_argument(
        "--no-index-natural",
        action="store_true",
        help="Disable natural numeric sorting for index generation",
    )
    parser.add_argument(
        "--apply-fixes",
        action="store_true",
        help="Shortcut for --fix-names --convert-type1 --write-index",
    )
    parser.add_argument(
        "--check-drums",
        action="store_true",
        help=(
            "Validate GM drum range: Channel 10 (MIDI channel 9) must use "
            f"note numbers {GM_DRUM_MIN}–{GM_DRUM_MAX}"
        ),
    )

    args = parser.parse_args(argv)

    deep = not args.no_deep
    index_natural = not args.no_index_natural

    # Apply convenience shortcut
    if args.apply_fixes:
        args.fix_names = True
        args.convert_type1 = True
        if not args.write_index:
            args.write_index = "INDEX.TXT"

    if not os.path.isdir(args.path):
        print(f"Not a directory: {args.path}", file=sys.stderr)
        return 2

    # Apply renaming / conversion / index generation
    renamed, converted, idx_file = apply_fixes(
        args.path,
        args.fix_names,
        args.convert_type1,
        args.write_index,
        args.index_all,
        args.index_uppercase,
        index_natural,
    )

    for a, b in renamed:
        print(f"[RENAMED] {a} -> {b}")
    for fn in converted:
        print(f"[CONVERTED] {fn}")

    if idx_file:
        print(f"[INDEX] wrote: {idx_file}")

    # Scan directory
    rows = scan_directory(args.path, deep=deep)

    # GM drum range validation
    if args.check_drums:
        print("\nGM Drum Range Validation (Channel 10: "
              f"{GM_DRUM_MIN}–{GM_DRUM_MAX})")
        for r in rows:
            bad = r.get("gm_drum_bad_notes", [])
            if bad:
                print(f"[DRUM-WARN] {r['name']}: out-of-range notes {bad}")
            else:
                print(f"[DRUM-OK]   {r['name']}")

    # Print summary table
    print("\nSummary Table:\n")
    print_table(rows)

    # Exports
    if args.csv:
        export_csv(args.csv, rows)
    if args.json:
        export_json(args.json, rows)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
