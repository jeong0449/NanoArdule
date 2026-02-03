# aps_arr.py — ARR save/load helpers for APS v0.27 (patched: SECTION roundtrip)

from __future__ import annotations
import os
import re
from typing import List, Tuple, Optional, Dict
from aps_core import ChainEntry


def _infer_sections_from_chain(chain: List[ChainEntry]) -> Dict[str, Tuple[int, int]]:
    """
    Infer section ranges from ChainEntry.section labels.

    Returns:
        Dict[name, (start0, end0)]  # 0-based inclusive indices

    Notes:
    - Only non-empty section names are exported.
    - If the same section name appears in multiple disjoint runs,
      it will be exported as name, name_2, name_3, ... to avoid collisions.
    """
    sections: Dict[str, Tuple[int, int]] = {}
    if not chain:
        return sections

    def _unique_name(base: str) -> str:
        if base not in sections:
            return base
        i = 2
        while f"{base}_{i}" in sections:
            i += 1
        return f"{base}_{i}"

    cur_name: Optional[str] = None
    cur_start: Optional[int] = None

    def _flush(end_idx: int):
        nonlocal cur_name, cur_start
        if cur_name and cur_start is not None and cur_start <= end_idx:
            name = _unique_name(cur_name)
            sections[name] = (cur_start, end_idx)
        cur_name = None
        cur_start = None

    for i, e in enumerate(chain):
        name = getattr(e, "section", None)
        if name is not None:
            name = str(name).strip()
        if not name:
            # Leaving/ending a section run
            if cur_name is not None:
                _flush(i - 1)
            continue

        # Entering a new run
        if cur_name is None:
            cur_name = name
            cur_start = i
            continue

        # Continuing same section run
        if name == cur_name:
            continue

        # Section name changed -> close previous run, start new
        _flush(i - 1)
        cur_name = name
        cur_start = i

    # Flush last run
    if cur_name is not None and cur_start is not None:
        _flush(len(chain) - 1)

    return sections


def _apply_sections_to_chain(chain: List[ChainEntry], sections: Dict[str, Tuple[int, int]]) -> None:
    """
    Apply section ranges onto ChainEntry.section labels.
    sections uses 0-based inclusive ranges.
    """
    if not chain or not sections:
        return

    n = len(chain)

    # Clear existing labels first (optional; helps make load deterministic)
    for e in chain:
        if hasattr(e, "section"):
            setattr(e, "section", None)

    # Apply in a stable order: by start index, then name
    for name, (s, e) in sorted(sections.items(), key=lambda kv: (kv[1][0], kv[0])):
        try:
            s0 = int(s)
            e0 = int(e)
        except Exception:
            continue
        if s0 > e0:
            s0, e0 = e0, s0
        s0 = max(0, min(s0, n - 1))
        e0 = max(0, min(e0, n - 1))
        for i in range(s0, e0 + 1):
            setattr(chain[i], "section", name)


def save_arr(path: str, chain: List[ChainEntry], bpm: int) -> None:
    """
    Save chain and BPM into a simple text ARR format.

    Also exports SECTION metadata inferred from ChainEntry.section:

        #ARR
        BPM=120

        #SECTION Verse 1 8
        #SECTION Chorus 9 16

        1=POP_P001.ADP
        2=POP_B001.ADP

        MAIN|1x2,2,1,2
        BARS|F,A,F,B
    """
    # Pool: unique filenames in order of appearance
    pool: List[str] = []
    for entry in chain:
        if entry.filename not in pool:
            pool.append(entry.filename)

    idx_map = {fn: i + 1 for i, fn in enumerate(pool)}

    # MAIN sequence
    seq_parts: List[str] = []
    for entry in chain:
        i = idx_map[entry.filename]
        rep = int(getattr(entry, "repeats", 1) or 1)
        if rep > 1:

            # Expand repeats so MAIN| never contains xN (or XN).
            try:
                n = max(1, int(rep))
            except Exception:
                n = 1
            seq_parts.extend([str(i)] * n)
        else:
            seq_parts.append(str(i))
    main_line = "MAIN|" + ",".join(seq_parts)

    # Optional BARS line (1:1 with MAIN entries). Default is F.
    bars_tokens = [str(getattr(e, "bars", "F") or "F").upper()[:1] for e in chain]
    has_non_full = any(t in ("A", "B") for t in bars_tokens)
    bars_line = "BARS|" + ",".join(bars_tokens) if has_non_full else None

    # SECTION lines inferred from ChainEntry.section (0-based -> 1-based)
    sections = _infer_sections_from_chain(chain)
    section_lines: List[str] = []
    for name, (s0, e0) in sorted(sections.items(), key=lambda kv: (kv[1][0], kv[0])):
        section_lines.append(f"#SECTION {name} {s0 + 1} {e0 + 1}")

    lines: List[str] = []
    lines.append("#ARR")
    lines.append(f"BPM={bpm}")
    lines.append("")

    # SECTION metadata (optional)
    if section_lines:
        lines.extend(section_lines)
        lines.append("")

    # POOL
    for i, fn in enumerate(pool, start=1):
        lines.append(f"{i}={fn}")
    lines.append("")
    lines.append(main_line)
    if bars_line:
        lines.append(bars_line)
    lines.append("")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_arr(path: str) -> Tuple[List[ChainEntry], Optional[int], dict]:
    """
    Parse an ARR file and restore its chain, BPM, and section metadata.

    Returns:
        (chain, bpm, sections)

        - chain: List[ChainEntry] (with .bars and .section restored when possible)
        - bpm: Optional[int]
        - sections: Dict[str, Tuple[int, int]]  # 0-based inclusive ranges
    """
    with open(path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    # Strip whitespace and ignore empty lines
    lines = [ln.strip() for ln in raw_lines if ln.strip()]

    bpm: Optional[int] = None
    pool_map: dict[int, str] = {}
    main_spec: Optional[str] = None
    bars_spec: Optional[str] = None
    sections: dict[str, tuple[int, int]] = {}

    for ln in lines:
        # Section definition: "#SECTION <name> <start> <end>" (ARR: 1-based)
        if ln.startswith("#SECTION"):
            parts = ln.split()
            if len(parts) >= 4:
                _, name, s, e = parts[:4]
                try:
                    s0 = int(s) - 1
                    e0 = int(e) - 1
                    sections[name] = (s0, e0)
                except ValueError:
                    pass
            continue

        # Ignore other comment lines
        if ln.startswith("#"):
            continue

        # BPM definition
        if ln.upper().startswith("BPM="):
            try:
                bpm = int(ln.split("=", 1)[1])
            except Exception:
                bpm = None
            continue

        # MAIN chain specification
        if ln.upper().startswith("MAIN|"):
            main_spec = ln.split("|", 1)[1].strip()
            continue

        # Optional bars selection line
        if ln.upper().startswith("BARS|"):
            bars_spec = ln.split("|", 1)[1].strip()
            continue

        # Pool entry
        if "=" in ln and ln.split("=", 1)[0].isdigit():
            idx_str, fn = ln.split("=", 1)
            try:
                idx = int(idx_str)
                pool_map[idx] = fn.strip()
            except ValueError:
                pass

    chain: List[ChainEntry] = []

    # Build chain from MAIN
    if main_spec:
        parts = [p.strip() for p in main_spec.split(",") if p.strip()]
        for p in parts:
            m = re.match(r"^(\d+)\s*[xX]\s*(\d+)$", p)
            if m:
                try:
                    idx = int(m.group(1))
                    rep = int(m.group(2))
                except ValueError:
                    continue
            else:
                try:
                    idx = int(p)
                except ValueError:
                    continue
                rep = 1

            fn = pool_map.get(idx)
            if not fn:
                continue
            chain.append(ChainEntry(fn, rep))

    # Apply BARS tokens (1:1 with MAIN entries)
    toks: List[str] = []
    if bars_spec:
        toks = [t.strip().upper()[:1] for t in bars_spec.split(",") if t.strip()]

    for i, e in enumerate(chain):
        t = toks[i] if i < len(toks) else "F"
        if t not in ("F", "A", "B"):
            t = "F"
        setattr(e, "bars", t)

    # Apply SECTION metadata onto ChainEntry.section for UI friendliness
    _apply_sections_to_chain(chain, sections)

    return chain, bpm, sections
