#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aps_core.py — APS v0.27 core structures and ADT/ADP loading.
"""

import os
import re
import struct
import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

  
try:
    from adc_adt2adp import parse_adt_text
except Exception as e:
    parse_adt_text = None
    raise RuntimeError(f"Failed to import adc_adt2adp.parse_adt_text: {e}")


HIT_CHAR = "■"

# GM 12-slot mapping (same as original APS)
GM12 = [
    (36, "KK", "KICK"), (38, "SN", "SNARE"), (42, "CH", "HH_CLOSED"),
    (46, "OH", "HH_OPEN"), (45, "LT", "TOM_LOW"), (47, "MT", "TOM_MID"),
    (50, "HT", "TOM_HIGH"), (51, "RD", "RIDE"), (49, "CR", "CRASH"),
    (37, "RM", "RIMSHOT"), (39, "CL", "CLAP"), (44, "PH", "HH_PEDAL"),
]

GRID_CODE_TO_STR = {0: "16", 1: "8T", 2: "16T"}
GRID_STR_TO_CODE = {"16": 0, "8T": 1, "16T": 2}


@dataclass
class Pattern:
    name: str
    path: str
    length: int
    slots: int
    grid: List[List[int]]
    grid_type: str
    slot_abbr: List[str]
    slot_note: List[int]
    slot_name: List[str]
    time_sig: str
    triplet: bool


    play_bars: int = 2
@dataclass
class ChainEntry:
    filename: str
    repeats: int = 1
    bars: str = "F"  # F=full, A=1st bar, B=2nd bar
    section: Optional[str] = None


def load_adt(path: str) -> Pattern:
    if parse_adt_text is None:
        raise RuntimeError("adt2adp.py 가 필요합니다.")
    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    # Effective playback length (default: 2 bars).
    # If ADT header contains PLAY_BARS=1, treat as a 1-bar pattern.
    # If header flag is absent, filename hint *_HNNN.ADT may be used as a fallback.
    play_bars = 2
    if re.search(r"^\s*PLAY_BARS\s*=\s*1\s*$", raw, flags=re.IGNORECASE | re.MULTILINE):
        play_bars = 1
    elif is_h_pattern_filename(os.path.basename(path)):
        play_bars = 1

    meta, slot_decl, grid, _norm = parse_adt_text(raw)

    length = int(meta["LENGTH"])
    slots = int(meta["SLOTS"])
    grid_type = str(meta["GRID"]).upper()
    time_sig = meta.get("TIME_SIG", "4/4")
    triplet = grid_type.endswith("T")

    slot_abbr, slot_note, slot_name = [], [], []
    for i in range(slots):
        sd = slot_decl[i]
        slot_abbr.append(sd["abbr"])
        slot_note.append(sd["note"])
        slot_name.append(sd.get("name", f"S{i}"))

    return Pattern(
        name=os.path.basename(path),
        path=path,
        length=length,
        slots=slots,
        grid=grid,
        grid_type=grid_type,
        slot_abbr=slot_abbr,
        slot_note=slot_note,
        slot_name=slot_name,
        time_sig=time_sig,
        triplet=triplet,
        play_bars=play_bars,
    )


def load_adp(path: str) -> Pattern:
    data = open(path, "rb").read()
    header_fmt = "<4sBBBBH B H B H I"
    header_size = struct.calcsize(header_fmt)

    (
        magic, version, grid_code, length, slots,
        ppqn, swing, tempo, reserved, adt_crc, payload_bytes
    ) = struct.unpack(header_fmt, data[:header_size])

    if magic != b"ADP2":
        raise ValueError("Not ADP2")
    if version != 22:
        raise ValueError("ADP version mismatch")

    payload = data[header_size: header_size + payload_bytes]

    grid = [[0]*slots for _ in range(length)]
    off = 0
    for step in range(length):
        count = payload[off]; off += 1
        for _ in range(count):
            hit = payload[off]; off += 1
            slot = (hit >> 2) & 0x0F
            acc = hit & 0x03
            if slot < slots:
                if acc > grid[step][slot]:
                    grid[step][slot] = acc

    triplet = GRID_CODE_TO_STR.get(grid_code, "16").endswith("T")
    grid_type = GRID_CODE_TO_STR.get(grid_code, "16")

    slot_abbr, slot_note, slot_name = [], [], []
    for i in range(slots):
        if i < len(GM12):
            n, a, nm = GM12[i]
            slot_abbr.append(a); slot_note.append(n); slot_name.append(nm)
        else:
            slot_abbr.append(f"S{i}"); slot_note.append(60); slot_name.append(f"SLOT{i}")

    return Pattern(
        name=os.path.basename(path),
        path=path,
        length=length,
        slots=slots,
        grid=grid,
        grid_type=grid_type,
        slot_abbr=slot_abbr,
        slot_note=slot_note,
        slot_name=slot_name,
        time_sig="4/4",
        triplet=triplet,
    )

def load_apt(path: str) -> Pattern:
    """
    APS hybrid pattern loader (.APT).
    APT 파일은 JSON으로 Pattern 필드를 직렬화한 간단한 포맷이다.
    """
    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    data = json.loads(raw)

    length = int(data["length"])
    slots = int(data["slots"])
    grid_type = str(data.get("grid_type", "16")).upper()
    time_sig = data.get("time_sig", "4/4")
    # triplet 정보가 없으면 GRID 타입에서 유추
    triplet = bool(data.get("triplet", grid_type.endswith("T")))

    slot_abbr = list(data["slot_abbr"])
    slot_note = list(data["slot_note"])
    slot_name = list(data["slot_name"])
    grid = data["grid"]

    return Pattern(
        name=data.get("name", os.path.basename(path)),
        path=path,
        length=length,
        slots=slots,
        grid=grid,
        grid_type=grid_type,
        slot_abbr=slot_abbr,
        slot_note=slot_note,
        slot_name=slot_name,
        time_sig=time_sig,
        triplet=triplet,
    )




def compute_timing(p: Pattern) -> Tuple[int, int, int, int]:
    try:
        num, den = p.time_sig.split("/")
        beats = int(num)
    except Exception:
        beats = 4
    bars = getattr(p, 'play_bars', 2)
    effective_len = p.length if bars == 2 else max(1, p.length // 2)
    steps_per_bar = effective_len // bars if bars else effective_len
    steps_per_beat = steps_per_bar // beats if beats else steps_per_bar
    return beats, bars, steps_per_beat, steps_per_bar


def describe_timing(p: Pattern) -> str:
    beats, bars, spb, spbar = compute_timing(p)
    tri = "triplet" if p.triplet else "straight"
    return f"{p.time_sig}, {bars} bars, GRID {p.grid_type} ({tri})"


def pattern_sort_key(fname: str):
    base, ext = os.path.splitext(fname)
    if "_" in base:
        genre = base.split("_", 1)[0]
    else:
        genre = base
    ext_rank = {'.adt': 0, '.apt': 0, '.adp': 1}.get(ext.lower(), 9)
    num = 9999
    kind_rank = 2
    m = re.search(r"_([pPbBhH])(\d{3})$", base)
    if m:
        kind = m.group(1).upper()
        num = int(m.group(2))
        kind_rank = {'P': 0, 'B': 1, 'H': 2}.get(kind, 9)
    return (genre.upper(), ext_rank, num, kind_rank, fname.lower())


def scan_patterns(root: str):
    out = []
    for f in os.listdir(root):
        if f.lower().endswith((".adt", ".apt", ".adp")):
            out.append(f)
    out.sort(key=pattern_sort_key)
    return out

# --- ADT meta utilities: PLAY_BARS=1 -----------------------------------------

def is_h_pattern_filename(fname: str) -> bool:
    """
    Return True if filename indicates a half (1-bar) pattern by convention, e.g. RCK_H001.ADT
    This is a *hint* only; authoritative flag is PLAY_BARS=1 in ADT header when present.
    """
    base = os.path.splitext(os.path.basename(fname))[0]
    return re.search(r"_H(\d{3})$", base, flags=re.IGNORECASE) is not None


def _normalize_newlines(raw: str) -> str:
    # Keep file ending with '\n' for stable diffs
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    if not raw.endswith("\n"):
        raw += "\n"
    return raw


def _find_header_insert_index(lines: List[str]) -> int:
    """
    Find a reasonable insertion point for meta keys.
    Strategy:
      - Insert after NAME= if present
      - Else insert near the top, before the first blank line (if any)
      - Else insert at line 0+ (top)
    """
    # After NAME=
    for i, ln in enumerate(lines[:80]):  # header is usually near the top
        if ln.strip().upper().startswith("NAME="):
            return i + 1

    # Before first blank line (keeps meta within header block)
    for i, ln in enumerate(lines[:200]):
        if ln.strip() == "":
            return i

    return 0


def set_adt_play_bars(path: str, bars: Optional[int]) -> bool:
    """
    Ensure ADT header contains (or does not contain) PLAY_BARS=1.

    - bars == 1 : ensure PLAY_BARS=1 exists (exactly once)
    - bars is None : remove PLAY_BARS=... lines (currently only PLAY_BARS=1 is used)
    - other values are rejected (returns False)

    Returns True if file was modified, False if no change was needed or on error.
    """
    if bars not in (1, None):
        return False

    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return False

    raw = _normalize_newlines(raw)
    lines = raw.split("\n")  # includes last empty after trailing newline

    # Remove any existing PLAY_BARS=... lines (case-insensitive)
    def is_play_bars_line(ln: str) -> bool:
        s = ln.strip().upper()
        return s.startswith("PLAY_BARS=")

    had_any = any(is_play_bars_line(ln) for ln in lines)
    if bars is None:
        if not had_any:
            return False
        new_lines = [ln for ln in lines if not is_play_bars_line(ln)]
        new_raw = "\n".join(new_lines)
        new_raw = _normalize_newlines(new_raw)
    else:
        # bars == 1
        # First, strip any PLAY_BARS=... (to avoid duplicates / conflicts), then insert PLAY_BARS=1
        new_lines = [ln for ln in lines if not is_play_bars_line(ln)]
        insert_at = _find_header_insert_index(new_lines)
        new_lines.insert(insert_at, "PLAY_BARS=1")
        new_raw = "\n".join(new_lines)
        new_raw = _normalize_newlines(new_raw)

        # If it already had exactly PLAY_BARS=1 at the right place, this may still rewrite.
        # To avoid needless rewrite, compare normalized raw.
        if new_raw == raw:
            return False

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_raw)
    except Exception:
        return False

    return True



def set_adt_name(path: str, name: Optional[str]) -> bool:
    """
    Ensure ADT header contains (or does not contain) NAME=... line.

    - name is a non-empty string: ensure NAME=<name> exists (exactly once)
    - name is None or empty: remove NAME=... lines

    Returns True if file was modified, False if no change was needed or on error.
    """
    try:
        raw = open(path, "r", encoding="utf-8", errors="ignore").read()
    except Exception:
        return False

    raw = _normalize_newlines(raw)
    lines = raw.split("\n")  # includes last empty after trailing newline

    def is_name_line(ln: str) -> bool:
        return ln.strip().upper().startswith("NAME=")

    had_any = any(is_name_line(ln) for ln in lines)

    nm = (name or "").strip()
    if not nm:
        # Remove NAME= lines
        if not had_any:
            return False
        new_lines = [ln for ln in lines if not is_name_line(ln)]
        new_raw = "\n".join(new_lines)
        new_raw = _normalize_newlines(new_raw)
    else:
        # Replace existing NAME= (first occurrence) and remove duplicates
        new_lines = []
        replaced = False
        for ln in lines:
            if is_name_line(ln):
                if not replaced:
                    new_lines.append(f"NAME={nm}")
                    replaced = True
                else:
                    # Drop duplicate NAME=
                    continue
            else:
                new_lines.append(ln)

        if not replaced:
            # Insert a new NAME= near the top
            insert_at = _find_header_insert_index(new_lines)
            new_lines.insert(insert_at, f"NAME={nm}")

        new_raw = "\n".join(new_lines)
        new_raw = _normalize_newlines(new_raw)

        if new_raw == raw:
            return False

    try:
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(new_raw)
    except Exception:
        return False

    return True


# --- Chain display utilities (Pattern Chain friendly metrics) -----------------
# These helpers are UI-agnostic and are intended to be used by aps_main / chain UI
# to show chain stats like Items/Unique/Bars and per-item start bar indices.
#
# NOTE: These functions do NOT modify any existing behavior and are safe to add.

def chain_entry_play_bars(entry) -> int:
    """
    Return effective playback bars for a ChainEntry.

    Rules (best-effort, no file I/O):
      - If filename indicates a half (1-bar) pattern (e.g. *_H001.ADT or *_h001.ADT), return 1
      - Otherwise, honor per-entry bars selector if present:
          * entry.bars == 'A' or 'B' => 1 bar (first/second bar only)
          * entry.bars missing or 'F' => 2 bars
    """
    try:
        fname = getattr(entry, "filename", "")
    except Exception:
        fname = ""
    # Half pattern by filename convention: always 1 bar.
    if is_h_pattern_filename(os.path.basename(str(fname))):
        return 1

    # Per-entry bars selector (F/A/B). This is UI/ARR-level info and should affect
    # chain length metrics and start-bar numbering.
    try:
        b = str(getattr(entry, "bars", "F") or "F").strip().upper()[:1]
    except Exception:
        b = "F"
    if b in ("A", "B"):
        return 1
    return 2


def chain_entry_total_bars(entry) -> int:
    """Return total bars contributed by one ChainEntry (play_bars * repeats)."""
    pb = chain_entry_play_bars(entry)
    try:
        rep = int(getattr(entry, "repeats", 1))
    except Exception:
        rep = 1
    if rep < 1:
        rep = 1
    return pb * rep


def compute_chain_metrics(chain: List["ChainEntry"]) -> Tuple[int, int, int]:
    """
    Compute (items, unique, bars) for the current chain.

    - items: number of chain entries (lines)
    - unique: number of unique pattern filenames referenced
    - bars: total playback bars (half patterns counted as 1 bar)
    """
    items = len(chain) if chain else 0
    if not chain:
        return 0, 0, 0
    uniq = len({str(getattr(e, "filename", "")) for e in chain})
    bars = sum(chain_entry_total_bars(e) for e in chain)
    return items, uniq, bars


def compute_chain_start_bars(chain: List["ChainEntry"]) -> List[int]:
    """
    Return a list of 1-based start bar numbers for each chain entry.

    Example:
      - entry0 starts at bar 1
      - entry1 starts at bar 1 + bars(entry0)
      - ...
    """
    starts: List[int] = []
    cur = 1
    for e in chain:
        starts.append(cur)
        cur += chain_entry_total_bars(e)
    return starts