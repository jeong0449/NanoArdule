# aps_arr.py — ARR save/load helpers for APS v0.27

from __future__ import annotations
import os
from typing import List, Tuple, Optional
from aps_core import ChainEntry


def save_arr(path: str, chain: List[ChainEntry], bpm: int) -> None:
    """
    체인과 BPM을 간단한 텍스트 ARR 포맷으로 저장한다.

    포맷 예시:
        # APS ARR v1
        BPM=120

        1=POP_P001.ADP
        2=POP_B001.ADP
        3=POP_P002.ADP

        MAIN|1x2,2,3x4

    - 앞부분의 숫자=파일명 부분은 POOL (패턴 목록)
    - MAIN 라인은 인덱스와 반복 횟수(xN)를 나열한 시퀀스
    """

    # 체인에서 등장하는 파일명을 순서대로 유니크하게 모은다.
    pool: List[str] = []
    for entry in chain:
        if entry.filename not in pool:
            pool.append(entry.filename)

    # 파일명 -> 번호 매핑
    idx_map = {fn: i + 1 for i, fn in enumerate(pool)}

    # MAIN 시퀀스 만들기
    seq_parts = []
    for entry in chain:
        i = idx_map[entry.filename]
        
        if int(getattr(entry, "repeats", 1) or 1) > 1:
            rep = int(getattr(entry, "repeats", 1) or 1)
            seq_parts.append(f"{i}x{rep}")
        else:
            seq_parts.append(str(i))

    main_line = "MAIN|" + ",".join(seq_parts)

    # Optional BARS line (1:1 with MAIN entries). Default is F.
    # - Tokens: F (full), A (1st bar), B (2nd bar)
    # - If all entries are F, omit the BARS| line for backwards compatibility.
    bars_tokens = [str(getattr(e, "bars", "F") or "F").upper()[:1] for e in chain]
    has_non_full = any(t in ("A", "B") for t in bars_tokens)
    bars_line = "BARS|" + ",".join(bars_tokens) if has_non_full else None

    lines: List[str] = []
    lines.append("#ARR")
    lines.append(f"BPM={bpm}")
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

        - chain: List[ChainEntry]
        - bpm: Optional[int] (None if BPM is not defined)
        - sections: Dict[str, Tuple[int, int]]
            Section name mapped to (start, end) indices
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
        # Section definition: "#SECTION <name> <start> <end>"
        # Must be handled before generic '#' comments
       
        if ln.startswith("#SECTION"):
            parts = ln.split()
            if len(parts) >= 4:
                _, name, s, e = parts[:4]
                try:
                    # ARR is 1-based, internal is 0-based (inclusive)
                    s0 = int(s) - 1
                    e0 = int(e) - 1
                    sections[name] = (s0, e0)
                except ValueError:
                    pass
            continue

        # Ignore other comment lines
        if ln.startswith("#"):
            continue

        # BPM definition: "BPM=<value>"
        if ln.upper().startswith("BPM="):
            try:
                bpm = int(ln.split("=", 1)[1])
            except Exception:
                bpm = None
            continue

        # MAIN chain specification: "MAIN|..."
        if ln.upper().startswith("MAIN|"):
            main_spec = ln.split("|", 1)[1].strip()
            continue

        # Optional bars selection line: "BARS|F,A,B"
        if ln.upper().startswith("BARS|"):
            bars_spec = ln.split("|", 1)[1].strip()
            continue

        # Pool entry: "<number>=<filename>"
        if "=" in ln and ln.split("=", 1)[0].isdigit():
            idx_str, fn = ln.split("=", 1)
            try:
                idx = int(idx_str)
                pool_map[idx] = fn.strip()
            except ValueError:
                pass

    chain: List[ChainEntry] = []

    # Build the main chain from MAIN specification
    if main_spec:
        parts = [p.strip() for p in main_spec.split(",") if p.strip()]
        for p in parts:
            # Format: "3x4" (index x repeats) or "3" (single repeat)
            if "x" in p:
                idx_str, rep_str = p.split("x", 1)
                try:
                    idx = int(idx_str)
                    rep = int(rep_str)
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

    # Apply optional BARS tokens (1:1 with MAIN entries).
    # If BARS| is missing, default everything to F (backwards compatibility).
    toks: List[str] = []
    if bars_spec:
        toks = [t.strip().upper()[:1] for t in bars_spec.split(",") if t.strip()]

    for i, e in enumerate(chain):
        t = toks[i] if i < len(toks) else "F"
        if t not in ("F", "A", "B"):
            t = "F"
        setattr(e, "bars", t)

    return chain, bpm, sections
