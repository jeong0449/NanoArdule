#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
adc-mkindex.py — Build /SYSTEM/INDEX.TXT from ADP v2.2 pattern files

What it does
- Scans a /PATTERNS directory for *.ADP (optionally recursive).
- Reads the ADP v2.2 header and extracts:
  GRID, LENGTH, SLOTS, PPQN, CRC16 (of normalized ADT text), and file size.
- Infers GENRE from the filename prefix before '_' (e.g., RCK_P001.ADP -> RCK).
- Writes a pipe-separated index file used by Ardule/APS UIs.

ADP v2.2 header layout
- struct "<4sBBBBH B H B H I"
  magic, ver, grid, length, slots, ppqn, swing, tempo, reserved, adt_crc16, payload_bytes

Usage
  python adc-mkindex.py --patterns ./SD/PATTERNS --out ./SD/SYSTEM/INDEX.TXT --recursive

Notes
- This tool does not modify pattern files; it only reads headers and writes INDEX.TXT.
"""


import argparse, pathlib, sys, struct, datetime, collections

ADP_MAGIC = b"ADP2"
ADP_VERSION = 22

def read_adp_header(path: pathlib.Path):
    with path.open("rb") as f:
        hdr = f.read(4+1+1+1+1+2+1+2+1+2+4)
    if len(hdr) < 20:
        raise ValueError("header too short")
    magic, ver, grid, length, slots, ppqn, swing, tempo, reserved, adt_crc, payload = struct.unpack(
        "<4sBBBBH B H B H I", hdr
    )
    if magic != ADP_MAGIC or ver != ADP_VERSION:
        raise ValueError("not ADP v2.2")
    size = path.stat().st_size
    return {
        "grid": int(grid),        # 0=16,1=8T,2=16T
        "length": int(length),    # 24/32/48
        "slots": int(slots),      # usually 12
        "ppqn": int(ppqn),        # info (96)
        "swing": int(swing),      # meta (0)
        "tempo": int(tempo),      # meta (0)
        "crc": int(adt_crc),      # CRC16 of normalized ADT
        "payload_bytes": int(payload),
        "size": int(size),
    }

def genre_from_name(stem: str) -> str:
    # Take prefix before '_' and clamp to 3 letters (uppercase).
    g = stem.split('_', 1)[0].upper() if '_' in stem else stem[:3].upper()
    if not g: g = "ETC"
    return g[:3]

def main():
    ap = argparse.ArgumentParser(description="Scan ADP v2.2 files and generate /SYSTEM/INDEX.TXT")
    ap.add_argument("--patterns", required=True, help="Path to the /PATTERNS directory containing .ADP files")
    ap.add_argument("--out", required=True, help="Output path for the generated INDEX.TXT")
    ap.add_argument("--recursive", action="store_true", help="Scan subdirectories recursively")
    ap.add_argument("--root", default="/PATTERNS", help="Root path label written into the INDEX header (default: /PATTERNS)")
    args = ap.parse_args()

    patdir = pathlib.Path(args.patterns)
    if not patdir.exists():
        print(f"[ERR] no such dir: {patdir}", file=sys.stderr)
        sys.exit(1)

    files = []
    if args.recursive:
        for p in patdir.rglob("*"):
            if p.is_file() and p.suffix.lower() == ".adp":
                files.append(p)
    else:
        for p in patdir.iterdir():
            if p.is_file() and p.suffix.lower() == ".adp":
                files.append(p)

    rows = []
    genre_counts = collections.Counter()

    for p in sorted(files, key=lambda x: x.name.upper()):
        try:
            hdr = read_adp_header(p)
        except Exception as e:
            # Skip invalid files.
            print(f"[SKIP] {p.name}: {e}")
            continue
        stem = p.stem
        gen = genre_from_name(stem)
        genre_counts[gen] += 1

        grid_str = {0:"16", 1:"8T", 2:"16T"}.get(hdr["grid"], "?")
        rows.append({
            "file": p.name,
            "title": stem,
            "gen": gen,
            "len": hdr["length"],
            "grid": grid_str,
            "slots": hdr["slots"],
            "ppqn": hdr["ppqn"],
            "kit": "GM_STD",     # not stored in ADP; keep placeholder for UI
            "size": hdr["size"],
            "crc": f"{hdr['crc']:04X}",
        })

    # write index
    outp = pathlib.Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    total = sum(genre_counts.values())
    genresum = ", ".join(f"{k}:{v}" for k,v in sorted(genre_counts.items()))

    with outp.open("w", encoding="utf-8") as w:
        w.write(f"; ARDULE INDEX v1\n")
        w.write(f"; GENERATED={ts}\n")
        w.write(f"; ROOT={args.root}\n")
        w.write(f"; TOTAL={total}\n")
        if genresum:
            w.write(f"; GENRES={genresum}\n")
        w.write("\n")
        w.write("#ID | FILE | GEN | LEN | GRID | SLOTS | PPQN | KIT | SIZE | CRC | TITLE\n")

        for idx, r in enumerate(rows, start=1):
            w.write(
                f"{idx:04d} | {r['file']:<14} | {r['gen']:<3} | {r['len']:>2}  | {r['grid']:<3}  | "
                f"{r['slots']:>2}   | {r['ppqn']:>3}  | {r['kit']:<7} | {r['size']:>6} | {r['crc']:<4} | {r['title']}\n"
            )

    print(f"[OK] INDEX written: {outp}  (TOTAL={total})")

if __name__ == "__main__":
    main()
