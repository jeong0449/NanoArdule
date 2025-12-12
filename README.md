# Ardule Project — Arduino Nano-based Drum Patternology Ecosystem

> **Note:** This repository is currently undergoing internal testing.  
> Components will be released sequentially as they become stable.

**Ardule** is a complete open ecosystem for drum-pattern creation, conversion, playback, and analysis.  
It integrates **Arduino-based real-time drum engines**, a Python-based pattern studio (APS), a curated pattern library,  
and a family of **lightweight pattern formats (ADT, ADP, ADS, ARR)**.

With the addition of the **ADC Toolchain (adc- prefix)**, Ardule now supports automated conversion of MIDI drum patterns into ADT format, enabling seamless integration of external rhythm material into the ecosystem.

---

# 🌐 Ecosystem Overview

## 1. Nano Ardule Player (Firmware)
A real-time drum pattern engine for **Arduino Nano / Nano Every**.

- ADS streaming engine  
- GM/GS/XG CH10 playback  
- Program Change kit switching  
- Layering / Splitting  
- LCD user interface  
- MicroSD pattern library  
- MIDI routing  

---

## 2. Ardule Pattern Studio — APS (PC Toolchain)
Python-based editor for pattern authoring:

- ADT text editor  
- ADT ↔ ADP converter  
- ARR chain editor → ADS compiler  
- Pattern preview & visualization  
- curses-based step sequencer  
- Pattern indexing & analysis  
- MIDI debug tools  

---

## 3. Pattern Formats

| Format | Purpose | Details |
|--------|---------|---------|
| **ADT** | Editable 2-bar text pattern | Human-readable velocity symbols |
| **ADP** | Binary runtime pattern | Compact, fast parsing |
| **ADS** | Performance stream | Compiled chain + metadata |
| **ARR** | Chain description | Sections, repeats, transitions |

---

## 4. ADC Toolchain (adc- prefix) — MIDI → ADT Converters  
Located in: `tools/`

The ADC Toolchain converts external MIDI drum patterns into **ADT v2.2/v2.2a** format.

### Tools

| Script | Description |
|--------|-------------|
| [`adc-midtool.py`](./tools/adc-midtool.py) | Unified MIDI manager (scan, rename to 8.3, Type1→0, INDEX.TXT, GM drum check, CSV/JSON) |
| [`adc-mid2adt.py`](./tools/adc-mid2adt.py) | MIDI → ADT conversion |
| [`adc-clean.py`](./tools/adc-clean.py) | Normalize ADT |
| [`adc-index.py`](./tools/adc-index.py) | Generate INDEX.TXT |
| [`adc-batchmid.py`](./tools/adc-batchmid.py) | Batch MIDI conversion |
| [`adc-adt2adp.py`](./tools/adc-adt2adp.py) | ADT → ADP wrapper |

### Example Workflow

```
python ./tools/adc-mid2adt.py input.mid -o pattern.adt
python ./tools/adc-clean.py pattern.adt
python ./tools/adc-adt2adp.py pattern.adt
```

---

# 🥁 Pattern Library

Includes (or supports) 2-bar patterns across genres:

- Rock, Funk, Jazz, Blues, Ballad, Pop  
- GM-compatible mapping  
- Velocity-aware notation  

---

# 🏗 Repository Structure

```
/firmware/      # Arduino firmware
/APS/           # Pattern Studio
/specs/         # Format specifications
/patterns/      # Pattern datasets
/tools/         # ADC toolchain (adc- scripts)
/docs/          # Manuals
/images/        # Diagrams, screenshots
```

---

# 🚀 Getting Started

```
git clone https://github.com/USERNAME/ardule.git
cd ardule
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
