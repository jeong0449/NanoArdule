# Genre Code Table (from `adc-split-drum-2bar-save.py`)

This project uses a short **3-letter genre code** as the prefix of generated pattern filenames, e.g. `RCK_P001.MID`.
The slicer script infers the code from the input MIDI filename using simple keyword matching.

> Note: These codes are used for **naming and indexing** only. They do not affect MIDI content.

## Genre codes

| Code | Full name |
|---|---|
| `RCK` | Rock |
| `BOS` | Bossa Nova |
| `FNK` | Funk |
| `JZZ` | Jazz |
| `BLU` | Blues |
| `POP` | Pop |
| `BAL` | Ballad |
| `LAT` | Latin / Afro-Cuban / Cha-cha |
| `SMB` | Samba |
| `WLZ` | Waltz |
| `SWG` | Swing |
| `SHF` | Shuffle |
| `REG` | Reggae |
| `MTL` | Metal |
| `HHP` | Hip-Hop |
| `RNB` | R&B (Rhythm & Blues) |
| `EDM` | EDM / Dance |
| `HSE` | House |
| `TNO` | Techno |
| `DRM` | Drums (default / fallback) |

## Where this comes from

The mapping is defined in the `GENRE_MAP` section of `adc-split-drum-2bar-save.py`.
If no keyword matches, the script falls back to the default code `DRM`.

Source: `adc-split-drum-2bar-save.py`.