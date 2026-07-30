# Genre Code Table (from `adc-split-drum-2bar-save.py`)

This project uses a short **3-letter genre code** as the prefix of generated pattern filenames, e.g. `RCK_P001.MID`.
The slicer script infers the code from the input MIDI filename using simple keyword matching.

> Note: These codes are used for **naming and indexing** only. They do not affect MIDI content.

## Genre Codes

| Code | Full name |
|------|-----------|
| RCK  | Rock |
| BNV  | Bossa Nova |
| FNK  | Funk |
| JZZ  | Jazz |
| BLU  | Blues |
| POP  | Pop |
| BAL  | Ballad |
| LAT  | Latin / Cha-cha-cha |
| AFC  | Afro-Cuban |
| SMB  | Samba |
| WLZ  | Waltz |
| SWG  | Swing |
| SHF  | Shuffle |
| REG  | Reggae |
| MTL  | Metal |
| HHP  | Hip-Hop |
| RAP  | Rap |
| RNB  | R&B (Rhythm & Blues) |
| EDM  | EDM / Dance |
| HSE  | House |
| TNO  | Techno |
| DRM  | Drums (default / fallback) |

## Where this comes from

The mapping is defined in the `GENRE_MAP` section of `adc-split-drum-2bar-save.py`.
If no keyword matches, the script falls back to the default code `DRM`.

Source: `adc-split-drum-2bar-save.py`.

## Inferring Genre Codes from MIDI Filenames

ADC PatternLab infers an initial genre code from keywords found in the MIDI filename. For example, `6BLUES.MID` is classified as `BLU`, `BOSSANOVA_01.MID` as `BNV`, and `RAP03.MID` as `RAP`.

Genre inference is performed using a list of case-insensitive regular expressions. The rules are evaluated from top to bottom, and the first matching genre code is returned. If no rule matches, the pattern is classified as `DRM`, which serves as the default fallback for generic drum patterns.

```python
import re
from pathlib import Path

GENRE_MAP = [
    # Rock / Bossa Nova / Funk / Jazz / Blues / Pop / Ballad
    (re.compile(r"rock", re.I), "RCK"),
    (re.compile(r"bossa|bossanova|bosa", re.I), "BNV"),
    (re.compile(r"funk", re.I), "FNK"),
    (re.compile(r"jazz", re.I), "JZZ"),
    (re.compile(r"blues?", re.I), "BLU"),
    (re.compile(r"pop", re.I), "POP"),
    (re.compile(r"ballad|bal", re.I), "BAL"),

    # Latin / Afro-Cuban / Cha-cha-cha
    (re.compile(r"latin", re.I), "LAT"),
    (re.compile(r"afrocub|afrocuba[n]?|afro[\s\-_]*cuba[n]?", re.I), "AFC"),
    (re.compile(r"chacha|cha[\s\-_]*cha", re.I), "LAT"),

    # Samba / Waltz / Swing / Shuffle / Reggae / Metal
    (re.compile(r"samba", re.I), "SMB"),
    (re.compile(r"waltz|wlz", re.I), "WLZ"),
    (re.compile(r"swing|swg", re.I), "SWG"),
    (re.compile(r"shuffle|shf", re.I), "SHF"),
    (re.compile(r"reggae", re.I), "REG"),
    (re.compile(r"metal", re.I), "MTL"),

    # Hip-Hop
    (re.compile(r"hip\s*-?\s*hop|hiphop|hhp", re.I), "HHP"),

    # Rap (avoids matching "TRAP")
    (re.compile(r"(?<![a-z])rap", re.I), "RAP"),

    # Rhythm & Blues
    (re.compile(r"r\s*&\s*b|randb|rnb", re.I), "RNB"),

    # EDM family
    (re.compile(r"edm|dance|dnc", re.I), "EDM"),

    # House / Techno
    (re.compile(r"house|hse", re.I), "HSE"),
    (re.compile(r"techno|tno", re.I), "TNO"),
]


def infer_genre(filename: str) -> str:
    """Infer an ADX genre code from a MIDI filename."""

    stem = Path(filename).stem

    for pattern, genre_code in GENRE_MAP:
        if pattern.search(stem):
            return genre_code

    return "DRM"
```

Example:

```python
>>> infer_genre("6BLUES.MID")
'BLU'

>>> infer_genre("HIP-HOP12.MID")
'HHP'

>>> infer_genre("OLD_RAP_03.MID")
'RAP'

>>> infer_genre("TRAP01.MID")
'DRM'
```

The purpose of this function is not to perform detailed musical genre classification, but to preserve useful metadata already embedded in MIDI filenames. The inferred genre serves as the initial value in PatternLab and can be changed by the user before exporting ADT or ADP files.
