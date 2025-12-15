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


@dataclass
class ChainEntry:
    filename: str
    repeats: int = 1
    section: Optional[str] = None


def load_adt(path: str) -> Pattern:
    if parse_adt_text is None:
        raise RuntimeError("adt2adp.py 가 필요합니다.")
    raw = open(path, "r", encoding="utf-8", errors="ignore").read()
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
    bars = 2
    steps_per_bar = p.length // bars if bars else p.length
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
    m = re.search(r"_([pPbB])(\d{3})$", base)
    if m:
        kind = m.group(1).upper()
        num = int(m.group(2))
        kind_rank = 0 if kind == 'P' else 1
    return (genre.upper(), ext_rank, num, kind_rank, fname.lower())


def scan_patterns(root: str):
    out = []
    for f in os.listdir(root):
        if f.lower().endswith((".adt", ".apt", ".adp")):
            out.append(f)
    out.sort(key=pattern_sort_key)
    return out
