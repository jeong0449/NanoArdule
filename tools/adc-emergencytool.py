#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-emergencytool.py (ADT-only, v1.0)

Emergency payload generator for Nano Ardule firmware.

Design decisions (finalized):
- Input format: **ADT only**
- Rationale:
  * ADT is the semantic authority (GRID, LENGTH, PLAY_BARS, TIME_SIG, NAME)
  * Execution time is not critical
  * Avoid fragile coupling to ADP binary cache formats
- Payload policy:
  * Always extract **1st bar (@A semantics)**
  * Bar length (steps) is derived from ADT header (MetaTime principle)
  * Payload stores exactly one bar, variable steps
- Output:
  * emergency_payload.h  (PROGMEM packed grid payload + offsets)
  * emergency_index.h    (UI catalog, ADT-derived metadata)
  * report.txt           (flash usage summary)

ADP parsing code has been intentionally removed.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Tuple

# Canonical drum slot count used by firmware
SLOTS_CANON = 12

# GRID code → steps per bar (4/4 base, MetaTime)
GRID_STEPS_PER_BAR_44 = {
    "16": 16,
    "8T": 12,
    "16T": 24,
}

@dataclass
class PatternBar:
    stem: str
    grid: str
    steps_in_bar: int
    levels: List[List[int]]  # [slot][step] 0..3


def _sanitize_ascii(s: str, maxlen: int) -> str:
    s = re.sub(r"[^A-Za-z0-9 _\-\.\+]", "_", s).strip()
    if not s:
        s = "NONAME"
    return s[:maxlen]


def infer_genre_from_stem(stem: str) -> str:
    m = re.match(r"^([A-Za-z]{3})[_\-]", stem)
    if m:
        return m.group(1).upper()
    return "DRM"


def ceil_div(a: int, b: int) -> int:
    return (a + b - 1) // b


def pack_2bit_levels_slot_major(levels: List[List[int]], steps: int) -> bytes:
    """
    Slot-major packing, 4 steps per byte:
      byte = s0 | s1<<2 | s2<<4 | s3<<6
    Steps are padded to multiple of 4 with rests.
    """
    steps_padded = ceil_div(steps, 4) * 4
    out = bytearray()

    for slot_levels in levels:
        sl = list(slot_levels[:steps])
        if len(sl) < steps:
            sl.extend([0] * (steps - len(sl)))
        if len(sl) < steps_padded:
            sl.extend([0] * (steps_padded - len(sl)))

        for i in range(0, steps_padded, 4):
            s0, s1, s2, s3 = sl[i:i+4]
            out.append((s0 & 0x03) | ((s1 & 0x03) << 2) | ((s2 & 0x03) << 4) | ((s3 & 0x03) << 6))

    return bytes(out)


def parse_adt_v22(path: Path) -> PatternBar:
    """
    Parse ADT v2.2a (ORIENTATION=STEP or SLOT).
    Extract 1st bar only, with step count derived from GRID (+ TIME_SIG if needed).
    """
    header = {}
    data_lines: List[str] = []

    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith(";"):
            continue
        if "=" in line and not re.fullmatch(r"[.\-xXoO]+", line):
            k, v = line.split("=", 1)
            header[k.strip().upper()] = v.strip()
            continue
        if re.fullmatch(r"[.\-xXoO]+", line):
            data_lines.append(line)

    grid = header.get("GRID", "16")
    if grid not in GRID_STEPS_PER_BAR_44:
        raise ValueError(f"Unsupported GRID={grid} in {path.name}")

    length = int(header.get("LENGTH", GRID_STEPS_PER_BAR_44[grid]))
    slots = int(header.get("SLOTS", str(SLOTS_CANON)))
    orientation = header.get("ORIENTATION", "SLOT").upper()

    steps_per_bar = GRID_STEPS_PER_BAR_44[grid]

    # MetaTime: first bar step count
    if length >= steps_per_bar:
        steps_in_bar = steps_per_bar
    else:
        steps_in_bar = length

    sym2lvl = {".": 0, "-": 1, "x": 2, "o": 3}

    def map_line(s: str, n: int) -> List[int]:
        s = s.ljust(n, ".")[:n]
        return [sym2lvl.get(ch.lower(), 0) for ch in s]

    # Decode full grid first
    full_steps = length
    levels_full = [[0] * full_steps for _ in range(slots)]

    if orientation == "STEP":
        if len(data_lines) < full_steps:
            raise ValueError(f"{path.name}: STEP orientation expects {full_steps} rows")
        for t in range(full_steps):
            row = map_line(data_lines[t], slots)
            for s in range(slots):
                levels_full[s][t] = row[s]
    else:  # SLOT
        if len(data_lines) < slots:
            raise ValueError(f"{path.name}: SLOT orientation expects {slots} rows")
        for s in range(slots):
            levels_full[s] = map_line(data_lines[s], full_steps)

    # Extract first bar and normalize slots
    levels_bar = [[0] * steps_in_bar for _ in range(SLOTS_CANON)]
    for s in range(min(slots, SLOTS_CANON)):
        for t in range(steps_in_bar):
            levels_bar[s][t] = levels_full[s][t]

    return PatternBar(
        stem=path.stem,
        grid=grid,
        steps_in_bar=steps_in_bar,
        levels=levels_bar,
    )


def build_headers(patterns: List[PatternBar], out_dir: Path) -> Tuple[Path, Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = bytearray()
    offsets: List[int] = []
    index_entries = []

    for pid, p in enumerate(patterns):
        packed = pack_2bit_levels_slot_major(p.levels, p.steps_in_bar)

        offsets.append(len(payload))
        payload.extend(bytes([pid & 0xFF, p.steps_in_bar & 0xFF]))
        payload.extend(packed)

        genre = infer_genre_from_stem(p.stem)
        code = _sanitize_ascii(p.stem, 12)
        name = _sanitize_ascii(p.stem.replace("_", " "), 16)
        index_entries.append((genre, code, name, p.steps_in_bar, p.grid))

    payload_h = out_dir / "emergency_payload.h"
    index_h = out_dir / "emergency_index.h"
    report = out_dir / "report.txt"

    def fmt_bytes(bs: bytes, cols: int = 16) -> str:
        h = [f"0x{b:02X}" for b in bs]
        return "\n".join(
            "  " + ", ".join(h[i:i+cols]) + ("," if i+cols < len(h) else "")
            for i in range(0, len(h), cols)
        )

    payload_h.write_text(
        "#pragma once\n"
        "#include <Arduino.h>\n\n"
        f"#define EMERGENCY_PATTERN_COUNT {len(patterns)}\n"
        f"#define EMERGENCY_SLOTS {SLOTS_CANON}\n\n"
        "// Record header: [patternId, steps_in_bar], followed by packed 2-bit grid\n"
        "const uint8_t emergencyPayload[] PROGMEM = {\n"
        f"{fmt_bytes(payload)}\n"
        "};\n\n"
        "const uint16_t emergencyOffsets[] PROGMEM = {\n"
        + "  " + ", ".join(str(o) for o in offsets) + "\n"
        "};\n",
        encoding="utf-8",
    )

    index_h.write_text(
        "#pragma once\n"
        "#include <Arduino.h>\n\n"
        "typedef struct {\n"
        "  char genre[4];\n"
        "  char code[13];\n"
        "  char name[17];\n"
        "  uint8_t steps;   // steps per bar\n"
        "  char grid[4];    // \"16\", \"8T\", \"16T\"\n"
        "} EmergencyIndexEntry;\n\n"
        f"const EmergencyIndexEntry emergencyIndex[{len(index_entries)}] PROGMEM = {{\n"
        + "\n".join(
            f'  {{"{g}", "{c}", "{n}", {st}, "{gr}"}},'
            for (g, c, n, st, gr) in index_entries
        )
        + "\n};\n",
        encoding="utf-8",
    )

    lines = [
        "Emergency payload report (ADT-only)",
        f"- patterns: {len(patterns)}",
        f"- payload bytes total: {len(payload)}",
        f"- offsets table bytes: {len(offsets) * 2}",
        f"- estimated flash bytes: {len(payload) + len(offsets) * 2}",
        "",
        "Per pattern:"
    ]
    for i, p in enumerate(patterns):
        grid_bytes = SLOTS_CANON * ceil_div(p.steps_in_bar, 4)
        rec_bytes = 2 + grid_bytes
        lines.append(f"{i:02d} {p.stem}  GRID={p.grid}  steps={p.steps_in_bar}  record_bytes={rec_bytes}")

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return payload_h, index_h, report


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate emergency payload headers from ADT directory (ADT-only).")
    ap.add_argument("input_dir", type=str, help="Directory containing *.ADT files")
    ap.add_argument("--out", type=str, default=".", help="Output directory for headers")
    args = ap.parse_args()

    in_dir = Path(args.input_dir)
    out_dir = Path(args.out)

    if not in_dir.is_dir():
        raise SystemExit(f"Input directory not found: {in_dir}")

    adt_files = sorted(p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() == ".adt")
    if not adt_files:
        raise SystemExit(f"No ADT files found in {in_dir}")

    patterns = [parse_adt_v22(p) for p in adt_files]
    payload_h, index_h, report = build_headers(patterns, out_dir)

    print(f"[OK] Wrote: {payload_h}")
    print(f"[OK] Wrote: {index_h}")
    print(f"[OK] Wrote: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
