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
        if entry.repeats == 1:
            seq_parts.append(str(i))
        else:
            seq_parts.append(f"{i}x{entry.repeats}")
    main_line = "MAIN|" + ",".join(seq_parts)

    lines: List[str] = []
    lines.append("# APS ARR v1")
    lines.append(f"BPM={bpm}")
    lines.append("")

    # POOL
    for i, fn in enumerate(pool, start=1):
        lines.append(f"{i}={fn}")
    lines.append("")
    lines.append(main_line)
    lines.append("")

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_arr(path: str) -> Tuple[List[ChainEntry], Optional[int]]:
    """
    ARR 파일을 읽어 체인과 BPM을 복원한다.
    - 반환값: (chain, bpm)
      bpm 라인이 없으면 bpm은 None
    """
    with open(path, "r", encoding="utf-8") as f:
        raw_lines = f.readlines()

    lines = [ln.strip() for ln in raw_lines if ln.strip()]

    bpm: Optional[int] = None
    pool_map: dict[int, str] = {}
    main_spec: Optional[str] = None

    for ln in lines:
        if ln.startswith("#"):
            continue
        if ln.upper().startswith("BPM="):
            try:
                bpm = int(ln.split("=", 1)[1])
            except Exception:
                bpm = None
            continue

        if ln.upper().startswith("MAIN|"):
            main_spec = ln.split("|", 1)[1].strip()
            continue

        # POOL 라인: "숫자=파일명"
        if "=" in ln and ln.split("=", 1)[0].isdigit():
            idx_str, fn = ln.split("=", 1)
            try:
                idx = int(idx_str)
                pool_map[idx] = fn.strip()
            except ValueError:
                pass

    chain: List[ChainEntry] = []

    if main_spec:
        parts = [p.strip() for p in main_spec.split(",") if p.strip()]
        for p in parts:
            # "3x4" 또는 "3" 형태
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

    return chain, bpm
