# Ardule Project — Arduino Nano-based Drum Patternology Ecosystem

> **Note:** This repository is currently undergoing internal testing.  
> Components will be released sequentially as they become stable.

**Ardule** is a complete open ecosystem for drum-pattern creation, conversion, playback, and analysis.  
It integrates **Arduino-based real-time drum engines**, a Python-based pattern studio (APS), a curated pattern library,  
and a family of **lightweight pattern formats (ADT, ADP, ARR, ADS)**.

With the addition of the **ADC Toolchain (adc- prefix)**, Ardule now supports automated conversion of MIDI drum patterns into ADT format, enabling seamless integration of external rhythm material into the ecosystem.

---

# 🌐 Ecosystem Overview

## 1. The Hardware: Nano Ardule

The hardware is assembled on a perfboard, where an Arduino Nano and other components are hand-wired and securely mounted.

The drum pattern player requires higher performance and therefore uses an **Arduino Nano Every**, while the MIDI controller firmware is intended for the classic **Arduino Nano**.  
Depending on the intended use, the Arduino board can be swapped via a socket.

For detailed hardware documentation, including schematics and implementation notes, see  
[`hardware.md`](./docs/hardware.md).


## 2. Nano Ardule Drum Pattern Player (Firmware)

## Firmware Scope

This repository primarily focuses on the **Nano Ardule Drum Pattern Player firmware**, which serves as the reference implementation of the Ardule pattern system. The firmware was originally designed around an ADT/ADP-based drum pattern playback engine, and has since been extended to support song-level playback through compiled ADS (Ardule Data Stream), as well as direct playback of Standard MIDI Files (Type 0), all implemented without relying on external MIDI playback libraries.

Another firmware variant, the **Nano Ardule MIDI Controller**, is also publicly available within this repository. This variant focuses on real-time MIDI control features such as program change, layering, and splitting, and includes experimental support for direct playback of Standard MIDI Files (Type 0), as demonstrated in a separate video (https://www.youtube.com/watch?v=ZyeiwCxAJcU). While it shares the same codebase, it is distinct in scope from the Drum Pattern Player firmware and is not intended as the primary reference implementation of the Ardule pattern system.


Another firmware variant, the **MIDI Controller** (e.g. a **Type-0 MIDI file
player** with program change, layering, splitting, and more; see the demo
video on YouTube: https://www.youtube.com/watch?v=ZyeiwCxAJcU), exists
internally and is not part of the public release at this time, but **may be
published in the future as the project evolves and matures**.

Each firmware variant is designed for a different Arduino Nano platform: the Drum Pattern Player firmware targets newer Arduino Nano variants with expanded memory, while the MIDI Controller firmware is intended for classic Arduino Nano–class boards. Although they share parts of the codebase and coexist within the same repository, the two firmwares differ in scope, hardware assumptions, and intended use.

---

## 3. Ardule Pattern Studio — APS

**Ardule Pattern Studio (APS)** is a lightweight, terminal-based PC application and toolchain for drum pattern authoring, validation, and playback.  
Originally developed to support Nano Ardule firmware by providing pattern data and verification tools, APS has evolved into a standalone application that can be used independently of the hardware.

Core features include:

- **ADT text-based pattern editor**
- **ADT ↔ ADP conversion tools**
- **ARR chain editor and ADS stream compiler**
- **Pattern preview, visualization, and timing validation**
- **curses-based step sequencer with real-time playback**
- **Pattern indexing and structural analysis**
- **Optional MIDI output and debugging utilities**  
  (APS can operate fully without MIDI hardware)

---

## 4. Pattern Formats

| Format | Purpose | Details |
|--------|---------|---------|
| **ADT** | Editable 2-bar text pattern | Human-readable velocity symbols |
| **ADP** | Binary runtime pattern | Compact, fast parsing |
| **ARR** | Chain description | Sections, repeats, transitions |
| **ADS** | Performance stream | Compiled chain + metadata |

> **Note on terminology**
>
> Historically, the “D” in **ADT / ADP / ADS** originated from *drum pattern*
> usage, as the Ardule project initially focused on percussion workflows.
>
> In the current specification and documentation, **“D” is defined as
> “Data”** to reflect the instrument-agnostic nature of the formats and the
> MetaTime principle, where all musical intent is fully resolved before
> playback.

---

## 5. ADC Toolchain (adc- prefix) — MIDI → ADT Converters  
Located in: `tools/`

The ADC Toolchain converts external MIDI drum patterns into **ADT v2.2/v2.2a** format.

### Tools

| Script | Description |
|--------|-------------|
| [`adc-midtool.py`](./tools/adc-midtool.py) | Unified MIDI manager for batch processing all .MID files in a directory (scan, 8.3 rename, Type-1→0, INDEX.TXT, GM drum check, CSV/JSON). |
| [`adc-mid2report.py`](./tools/adc-mid2report.py) | Integrated MIDI report tool with triplet-aware subdivision analysis and ADT conversion hints. |
| [`adc-split-drum-2bar-save.py`](./tools/adc-split-drum-2bar-save.py) | CH10-only 2-bar MIDI slicer that saves <GEN>_Pnnn patterns, with optional grid PNG and A4 PDF export. |
| [`adc-drum-sim-matrix.py`](./tools/adc-drum-sim-matrix.py) | Compute all-pairs similarity matrices (Hamming/Cosine) for 2-bar CH10 drum pattern MIDI files using a 12-slot × N-column binary grid. |
| [`adc-mid2adt.py`](./tools/adc-mid2adt.py) | Convert 2-bar drum MIDI files to ADT v2.2a with auto grid detection and velocity symbols (. - X O). |
| [`adc-adt2adp.py`](./tools/adc-adt2adp.py) | Convert ADT v2.2a drum patterns to ADP v2.2 binary cache (fast load), with canonical velocity symbols (. - X O). |
| [`adc-mkindex.py`](./tools/adc-mkindex.py) | Scan ADP v2.2a pattern files and generate /SYSTEM/INDEX.TXT for Ardule/APS (genre, grid, length, CRC, size). |
| [`adc-arrtool.py`](./tools/adc-arrtool.py) | Process ARR files to expand pattern chains, resolve bar structure, and generate song-level data for ADS compilation and playback. |


### Example Workflow

```
python .\tools\adc-midtool.py
python .\tools\adc-mid2report.py .\INPUT.MID
python .\tools\adc-split-drum-2bar-save.py .\6AFROCUB.MID --genre LAT --export-grid --grid-pdf --start 31
python .\tools\adc-split-drum-2bar-save.py --print-genre-only .\6AFROCUB.MID
python .\tools\adc-mid2adt.py --in-dir MID --out-dir ADT
python .\tools\adc-adt2adp.py --in-dir ADT --out-dir ADP
python .\tools\adc-mkindex.py --patterns .\ADP --out ..\SD\SYSTEM
python .\tools\adc-arrtool.py --format both .\patterns\SONG_001.ARR --countin 4
```

---

# 🥁 Pattern Library

Includes (or supports) 2-bar patterns across genres:

- Rock, Funk, Jazz, Blues, Ballad, Pop  
- GM-compatible mapping  
- Velocity-aware notation  

---

## Common Execution Environment (APS & ADC)

The following execution environment is shared by **Ardule Pattern Studio (APS)** and the **ADC Toolchain**.  
This configuration is recommended for reliable operation across pattern editing, conversion, analysis, and playback.

### Python

- **Python 3.11.6**  
  Installed from **https://www.python.org**  
  > Microsoft Store Python distributions are not recommended due to known issues with terminal handling
  > (`curses`) and MIDI backends.

### Required Python Libraries

- `mido`
- `python-rtmidi`
- `windows-curses` (Windows only)

These libraries are required by both APS and ADC tools for MIDI handling, terminal-based UI,
and consistent runtime behavior.

### External Tools

- **Ghostscript**  
  Required by ADC tools that generate **PDF outputs** (e.g. drum grid visualization and A4 pattern sheets).

  Ghostscript must be available in the system `PATH`.

### Platform

- Windows 10 / Windows 11
- Command Prompt, PowerShell, or Windows Terminal

> APS and ADC tools can be used without MIDI hardware for editing, conversion, visualization, and analysis.  
> MIDI output is only required when using real-time playback or preview features.

---

# 🏗 Repository Structure

```
/firmware/      # Arduino firmware
/APS/           # Ardule Pattern Studio (python scripts)
/specs/         # Format specifications
/patterns/      # Pattern datasets
/tools/         # ADC toolchain (adc- python scripts)
/docs/          # Manuals and related documents
/images/        # Diagrams, screenshots
```

---

# 🚀 Getting Started

```
git clone https://github.com/jeong0449/NanoArdule.git
cd NanoArdule
```

---

# 🎵 Using Nano Ardule Player

### Upload Firmware
1. Install Arduino IDE  
2. Open `/firmware/`  
3. Select Nano / Nano Every  
4. Upload  

### SD Layout

```
/patterns/
    RCK_P001.ADP
/index.txt
```

---

# 🧰 Running APS

```
pip install -r APS/requirements.txt
python APS/aps_main.py
```

---

# 📜 Format Summary

- **ADT:** Editable text grid  
- **ADP:** Binary packed  
- **ADS:** Compiled stream  
- **ARR:** Human-readable chain  

---

# 🧪 Patternology Principles

- Lightweight (fits in 2 KB RAM)  
- Transparent, readable formats  
- Deterministic playback (ADS)  
- Modular APS ↔ firmware separation  
- Inspired by vintage drum machines  

---

# 🤝 Contributing

PRs and Issues welcome.

---

# 📜 License

MIT License.

---

# 📬 Contact

Use GitHub Issues for questions and suggestions.
---

## 📚 Documentation

Detailed documentation is organized by topic under the `docs/` directory.

- [Project overview](./docs/overview.md)
- [Architecture]
- [Nano Ardule Drum Pattern Player firmware]
- [Ardule Pattern Studio (APS) Keymap](./APS/APS_Keymap_2025-12-21.md)
- [ADT v2.2a specification](./specs/ADT_v2.2a.md)
- [ADP specification](./specs/ADP_specification.md)
- [ADC toolchain manuals]
- [Design Trade-offs in ADP: Fixed Steps and 2-Bar Patterns](./docs/ADP_design_tradeoffs.md)

> Some documents are placeholders and will be expanded in future updates.
