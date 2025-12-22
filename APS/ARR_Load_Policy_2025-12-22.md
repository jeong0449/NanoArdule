# ARR Load Policy (APS)

This document defines the **ARR loading policy** for APS (Ardule Pattern Studio).
It specifies how a source ARR is applied to the currently edited chain (target),
including chain entries, sections, and metadata handling.

---

## 0. Terminology

- **target**  
  The pattern chain currently being edited in APS.

- **source**  
  The ARR file being loaded.

- **ins**  
  The insertion index in the target chain (cursor position or append point).

- **m**  
  Number of chain entries in the source ARR.

- **section**  
  A metadata range attached to the chain, defined by start–end indices.

---

## 1. Core Principles

1. ARR loading is treated as **inserting or appending** the source chain into the target chain.
2. The chain itself is a **linear time axis** without implicit loops.
3. Sections are **metadata only** and must not break the chain structure.
4. ARR loading should **always succeed if possible**; conflicts are resolved by
   renaming and offsetting, not by rejection or silent overwrite.

---

## 2. Chain Entry Handling

- Source chain entries are inserted into the target chain while preserving:
  - order
  - repeat counts
- Insertion positions:
  - **Insert**: at index `ins`
  - **Append**: at `len(target)`

---

## 3. Target Section Handling (Split Rule)

Existing sections in the target are processed relative to the insertion point `ins`.

### 3.1 Sections Completely Before the Insertion Point

Condition:
```
section.end < ins
```

- No changes are applied.

---

### 3.2 Sections Covering the Insertion Point (Split)

Condition:
```
section.start < ins <= section.end
```

Given an original section:
```
S = [a .. b]
```

It is replaced by two sections:

- **Left section**
  - Name: `S_L`
  - Range: `[a .. ins - 1]`

- **Right section**
  - Name: `S_R`
  - Range: `[ins + m .. b + m]`

The original section `S` is removed.

---

### 3.3 Sections Completely After the Insertion Point

Condition:
```
section.start >= ins
```

- Apply offset `+m` to both start and end.
- Section name is preserved.

---

## 4. Source Section Handling (Import Rule)

All sections defined in the source ARR are imported into the target.

### 4.1 Name Prefix

- Every source section name is prefixed with:
```
i_
```

Examples:
- `Verse` → `i_Verse`
- `Chorus` → `i_Chorus`

This prefix unconditionally marks imported sections.

---

### 4.2 Range Offset

- Source section ranges are offset by the insertion index `ins`.

---

### 4.3 Name Uniqueness

- Semantic name conflicts are **not checked**.
- If an identical name already exists, a numeric suffix is appended:
  - `i_Verse`, `i_Verse2`, `i_Verse3`, ...

This guarantees uniqueness without merging semantics.

---

## 5. #PLAY Handling

- `#PLAY` in the source ARR is treated as **metadata**.
- Default behavior:
  - Target playback behavior is **not modified**.
- Optional behavior:
  - The `#PLAY` position may be stored with offset applied, as a reference hint.

---

## 6. Validation and Error Handling

- Missing pattern files referenced by the source:
  - Loading proceeds.
  - Existing runtime warning mechanisms are used during playback.
- Invalid or out-of-range section definitions:
  - The affected sections are ignored.
  - Loading continues.

---

## 7. Policy Summary

> ARR loading applies the source chain to the target chain via insertion or append.  
> Target sections crossing the insertion point are split into `_L` and `_R`.  
> Source sections are imported with an `i_` prefix and offset ranges.  
> Section conflicts are resolved by renaming, not merging.  
> The chain load operation should succeed whenever possible.

---

_Last updated: 2025-12-22_
