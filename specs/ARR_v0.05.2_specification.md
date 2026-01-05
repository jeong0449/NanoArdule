# ARR Specification v0.05.2
*(Text clarification update – backward compatible with v0.05.1)*

작성일: 2026-01-06  
상태: Clarification / Documentation Update Only

---

## 1. Design Intent (Non-Goals Included)

ARR is a **structural arrangement format**, not a visual or timing-annotated format.

ARR intentionally:
- Describes **pattern order** and **section labels**
- Uses **dictionary-based pattern references**
- Remains **stable, minimal, and human-readable**

ARR intentionally does **NOT**:
- Store bar numbers or timing offsets
- Store derived metrics (total bars, section length, etc.)
- Encode UI- or display-specific decorations

All derived information (bar positions, section lengths, playback duration, etc.)  
**MUST be computed by the host application** (e.g. APS).

---

## 2. File Structure Overview

An ARR file consists of the following logical parts:

1. Global directives (e.g. `#COUNTIN`)
2. Section metadata (`#SECTION`)
3. Optional playback script (`#PLAY ... #ENDPLAY`)
4. Format/version declaration
5. Global parameters (e.g. BPM)
6. Pattern dictionary
7. Main chain definition (`MAIN|...`)

---

## 3. Global Directives

### 3.1 `#COUNTIN`

```text
#COUNTIN NONE
#COUNTIN 1
#COUNTIN 2
```

Defines count-in bars before playback begins.

- `NONE` means no count-in
- Numeric values represent bar count
- Count-in bars are **not part of the MAIN chain**

---

## 4. Section Metadata

### 4.1 `#SECTION`

```text
#SECTION <SectionName> <StartIndex> <EndIndex>
```

Defines a section label for a range of MAIN chain entries.

Important notes:
- Indices are **1-based**
- Indices refer to **MAIN chain entry positions**
- Indices do **NOT** refer to dictionary IDs

---

## 5. Playback Script (Optional)

### 5.1 `#PLAY ... #ENDPLAY`

The `#PLAY` block defines an **optional playback script**.
Implementations MAY ignore this block and rely solely on `MAIN`.

---

### 5.2 Token Semantics in `#PLAY`

Within a `#PLAY` block:

- **String tokens** → section labels
- **Numeric tokens** → dictionary pattern IDs (played once)

ARR does **NOT** support repeat-count semantics in `#PLAY`.

---

## 6. Pattern Dictionary

```text
1=AFC_P002.ADT
2=AFC_P003.ADT
```

- Integer key → pattern filename mapping

---

## 7. MAIN Chain Definition

```text
MAIN|1,2,3,2,4,5,6,7,8,8
```

Defines the primary playback chain using dictionary IDs.

---

## 8. Summary of Parsing Rules

| Element | Meaning | Notes |
|-------|--------|-------|
| `N=FILE` | Pattern dictionary entry | Integer key |
| `MAIN|...` | Primary pattern chain | Dictionary IDs |
| `#SECTION A B C` | Section label | MAIN entry indices |
| `#PLAY` | Playback script | Optional |

---

## 9. Backward Compatibility

ARR v0.05.2 introduces **no syntax changes**.
It is fully backward compatible with v0.05.1.

---

*End of ARR Specification v0.05.2*
