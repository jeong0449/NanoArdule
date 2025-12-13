#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-adt2adp.py — ADT v2.2a → ADP v2.2 batch converter

Purpose
- Convert ADT text drum patterns into ADP v2.2 binary cache files for fast playback.

Key behaviors
- Detect STEP vs SLOT body orientation and normalize internally to STEP.
- Support LENGTH: 24/32/48 and GRID: 16/8T/16T.
- Write CRC16 (CCITT) of the normalized ADT text into the ADP header for change detection.

Velocity symbols (ADT v2.2a canonical)
- '.' : rest (level 0)
- '-' : soft (level 1)
- 'x'/'X' : medium (level 2)
- 'o'/'O' : strong/accent (level 3)

CLI
- Single file:
    python adc-adt2adp.py input.adt
- Batch:
    python adc-adt2adp.py --in-dir ./ADT --recursive --out-dir ./ADP

Dependencies
- Standard library only (no extra installation required)
"""


import argparse, pathlib, re, struct, sys

ADT_VERSION = "ADT v2.2a"
ADP_MAGIC = b"ADP2"
ADP_VERSION = 22
GRID_CODE = {"16": 0, "8T": 1, "16T": 2}

BODY_OK = {'.', '-', 'x', 'X', 'o', 'O', '^'}  # '^' accepted as legacy strong

def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF) -> int:
    c = init
    for b in data:
        c ^= (b << 8)
        for _ in range(8):
            c = ((c << 1) ^ poly) & 0xFFFF if (c & 0x8000) else ((c << 1) & 0xFFFF)
    return c

def acc_from_char(ch: str) -> int:
    if ch == '-': return 0
    if ch == '.': return 1
    if ch in ('o','O'): return 2
    if ch in ('x','X','^'): return 3
    return 0

def normalize_body_line(s: str) -> str:
    # Semicolon comments (;) are removed earlier
    s = s.strip()
    out = []
    for ch in s:
        if ch in BODY_OK:
            out.append(ch)
    return ''.join(out)

def parse_adt_text(txt: str):
    """
    반환:
      meta = {NAME, TIME_SIG, GRID, LENGTH(int), SLOTS(int), KIT, ORIENTATION}
      slots: list(12) of {abbr, note(int), name}
      grid:  LENGTH x SLOTS (acc 0..3) — STEP 기준
      norm_text: 정규화된 ADT(헤더+본문 STEP) → CRC 용
    """
    # Default metadata
    meta = {
        "NAME": "UNTITLED",
        "TIME_SIG": "4/4",
        "GRID": "16",
        "LENGTH": 32,
        "SLOTS": 12,
        "KIT": "GM_STD",
        "ORIENTATION": "STEP",
    }
    slot_decl = [None]*12
    body_lines_raw = []

    # 1) Scan lines (strip comments; key=value; SLOT declarations; body)
    for raw in txt.splitlines():
        line = raw.split(';', 1)[0].strip()
        if not line:
            continue
        m = re.match(r'^([A-Za-z0-9_]+)\s*=\s*(.+)$', line)
        if m:
            k = m.group(1).upper().strip()
            v = m.group(2).strip()
            if k in meta:
                meta[k] = v if k not in ("LENGTH","SLOTS") else int(v)
            elif k.startswith("SLOT"):
                try:
                    idx = int(k[4:])
                except:
                    continue
                if not (0 <= idx <= 11): continue
                # SLOTn=ABBR@NOTE[,NAME]
                abbr, note, name = "??", 0, ""
                if '@' in v:
                    a, rest = v.split('@', 1)
                    abbr = a.strip().upper()
                    if ',' in rest:
                        note_s, name = rest.split(',', 1)
                        note = int(note_s.strip())
                        name = name.strip()
                    else:
                        note = int(rest.strip())
                slot_decl[idx] = {"abbr": abbr, "note": note, "name": name}
            else:
                # 기타 키 무시
                pass
        else:
            body_lines_raw.append(normalize_body_line(line))

    L, S = meta["LENGTH"], meta["SLOTS"]

    # 2) Determine body orientation
    ori = str(meta.get("ORIENTATION","STEP")).upper()
    if ori not in ("STEP","SLOT"):
        # Auto-detect
        if len(body_lines_raw) >= L and all(len(ln)==S for ln in body_lines_raw[:L]):
            ori = "STEP"
        elif len(body_lines_raw) >= S and all(len(ln)==L for ln in body_lines_raw[:S]):
            ori = "SLOT"
        else:
            ori = "STEP"

    # 3) Body -> STEP-major grid
    grid = [[0]*S for _ in range(L)]
    if ori == "STEP":
        if len(body_lines_raw) < L:
            raise ValueError("BODY lines < LENGTH (STEP)")
        for i in range(L):
            row = body_lines_raw[i]
            if len(row) != S:
                raise ValueError(f"STEP row length != SLOTS at line {i+1}")
            for j,ch in enumerate(row):
                grid[i][j] = acc_from_char(ch)
    else:  # SLOT
        if len(body_lines_raw) < S:
            raise ValueError("BODY lines < SLOTS (SLOT)")
        for j in range(S):
            col = body_lines_raw[j]
            if len(col) != L:
                raise ValueError(f"SLOT row length != LENGTH at slot {j}")
            for i,ch in enumerate(col):
                grid[i][j] = acc_from_char(ch)

    # 4) Fill missing SLOT declarations (GM 12-slot default)
    GM12 = [
        (36,"KK","KICK"), (38,"SN","SNARE"), (42,"CH","HH_CL"), (46,"OH","HH_OP"),
        (45,"LT","TOM_L"), (47,"MT","TOM_M"), (50,"HT","TOM_H"), (51,"RD","RIDE"),
        (49,"CR","CRASH"), (37,"RM","RIM"),  (39,"CL","CLAP"),  (44,"PH","HH_PED"),
    ]
    for i in range(12):
        if slot_decl[i] is None:
            n,a,nm = GM12[i]
            slot_decl[i] = {"abbr":a, "note":n, "name":nm}

    # 5) Normalized text (always STEP + core meta) -> CRC
    norm = []
    norm.append(f"; {ADT_VERSION}")
    for k in ("NAME","TIME_SIG","GRID","LENGTH","SLOTS","KIT"):
        norm.append(f"{k}={meta[k]}")
    norm.append("ORIENTATION=STEP")
    for i in range(12):
        sd = slot_decl[i]
        norm.append(f"SLOT{i}={sd['abbr']}@{sd['note']},{sd['name']}")
    # Body (STEP-major)
    lut = {0:'.', 1:'-', 2:'X', 3:'O'}  # canonical output symbols
    for i in range(L):
        norm.append(''.join(lut[a] for a in grid[i]))
    norm_text = ("\n".join(norm) + "\n").encode("utf-8")

    # Internally, ORIENTATION is fixed to STEP
    meta["ORIENTATION"] = "STEP"
    return meta, slot_decl, grid, norm_text

def encode_adp(meta, grid, adt_crc16: int) -> bytes:
    """
    ADP v2.2 헤더(리틀엔디언):
      4s   magic "ADP2"
      B    version (22)
      B    grid  (0=16, 1=8T, 2=16T)
      B    length (24/32/48)
      B    slots  (보통 12)
      H    ppqn   (정보용 96 고정)
      B    swing  (메타용, 여기선 0)
      H    tempo  (메타용, 여기선 0)
      B    reserved (0)
      H    adt_crc16
      I    payload_bytes
    payload:
      for step in 0..L-1:
        u8 count
        count * u8 hit  (hit = (slot<<2) | acc)  ; acc 0..3, slot 0..11
    """
    grid_code = GRID_CODE.get(str(meta["GRID"]).upper(), 0)
    length = int(meta["LENGTH"])
    slots  = int(meta["SLOTS"])
    ppqn   = 96
    swing  = 0
    tempo  = 0
    reserved = 0

    # Build payload
    payload = bytearray()
    for i in range(length):
        hits = []
        for j in range(slots):
            acc = grid[i][j]
            if acc > 0:
                hits.append(((j & 0x0F) << 2) | (acc & 0x03))
        payload.append(len(hits) & 0xFF)
        payload.extend(hits)

    payload_bytes = len(payload)
    header = struct.pack(
        "<4sBBBBH B H B H I",
        ADP_MAGIC, ADP_VERSION, grid_code, length, slots,
        ppqn, swing, tempo, reserved, adt_crc16, payload_bytes
    )
    return header + payload

def convert_file(in_path: pathlib.Path, out_path: pathlib.Path, overwrite=False):
    if not in_path.exists():
        return False, f"no such file: {in_path}"
    if out_path.exists() and not overwrite:
        return False, f"exists: {out_path.name} (use --overwrite)"

    raw = in_path.read_text(encoding="utf-8", errors="ignore")
    meta, slots, grid, norm = parse_adt_text(raw)
    adt_crc = crc16_ccitt(norm)
    blob = encode_adp(meta, grid, adt_crc)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(blob)
    return True, f"ok: {in_path.name} -> {out_path.name} (L={meta['LENGTH']}, GRID={meta['GRID']})"

def iter_adt_files(root: pathlib.Path, recursive=False):
    if recursive:
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower()==".adt":
                yield p
    else:
        yield from root.glob("*.adt")
        yield from root.glob("*.ADT")

def main():
    ap = argparse.ArgumentParser(description="Convert ADT (v2.2a) text patterns to ADP v2.2 binary cache files.")
    ap.add_argument("input", nargs="?", help="Input ADT file path")
    ap.add_argument("--in-dir", type=str, help="Input folder (batch convert .ADT files)")
    ap.add_argument("--out-dir", type=str, help="Output folder (default: same as input)")
    ap.add_argument("--recursive", action="store_true", help="Recursively search subfolders (with --in-dir)")
    ap.add_argument("--overwrite", action="store_true", help="Overwrite existing .ADP files")
    args = ap.parse_args()

    if args.in_dir:
        in_root = pathlib.Path(args.in_dir)
        if not in_root.exists():
            print(f"[ERR] no such dir: {in_root}", file=sys.stderr); sys.exit(1)
        out_root = pathlib.Path(args.out_dir) if args.out_dir else in_root
        total=ok=0
        for p in iter_adt_files(in_root, args.recursive):
            total += 1
            out = (out_root / p.stem).with_suffix(".ADP")
            try:
                success, msg = convert_file(p, out, overwrite=args.overwrite)
            except Exception as e:
                success, msg = False, f"error: {p.name}: {e}"
            print(("[OK] " if success else "[SKIP] ") + msg)
            if success: ok += 1
        print(f"\nDone. {ok}/{total} converted.")
        return

    # Single-file mode
    if not args.input:
        ap.print_help(); sys.exit(0)

    in_path = pathlib.Path(args.input)
    out_path = (pathlib.Path(args.out_dir) if args.out_dir else in_path.parent / in_path.stem).with_suffix(".ADP")

    try:
        success, msg = convert_file(in_path, out_path, overwrite=args.overwrite)
    except Exception as e:
        success, msg = False, f"error: {in_path.name}: {e}"
    print(("[OK] " if success else "[ERR] ") + msg)
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
