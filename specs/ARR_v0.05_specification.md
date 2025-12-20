# ARR v0.05 Specification
**Ardule Chain File – Transitional Specification**

---

## 1. Purpose

ARR v0.05 is a **transitional, human-readable chain format** used by APS (Ardule Pattern Studio)
to describe the playback order of drum patterns.

This version intentionally:

- Treats **sections as labels (metadata)**, not structural elements
- Preserves compatibility with the existing chain editor and playback engine
- Serves as a stable bridge toward a future ARR DSL (e.g. v0.1), without enforcing it

ARR v0.05 is designed to be:

- Easy to read and review by humans
- Safely editable by APS without complex parsing logic
- Backward-compatible during iterative development

---

## 2. File Structure Overview

An ARR v0.05 file consists of:

1. Optional comment / metadata lines (starting with `#`)
2. A single MAIN playback line (machine-oriented)
3. No mandatory DSL blocks

Example:

```
#COUNTIN CountIn_HH
#SECTION Verse 1 4
#SECTION Chorus 5 8
#PLAY Verse Chorus Verse

MAIN|1x2,2,3x4
```

---

## 3. Comment and Metadata Lines

All metadata lines begin with `#` and are ignored by the playback engine unless explicitly stated.

### 3.1 `#COUNTIN` (Count-in Mode)

```
#COUNTIN <mode>
```

Defines the count-in behavior before playback starts.

#### Supported modes (v0.05)

- `CountIn_HH`  
  Hi-hat based count-in (default APS behavior)
- `OFF`  
  No count-in

Additional modes (e.g. `CountIn_SD`, `CountIn_RIM`) may be supported by APS implementations
but are not required by this specification.

#### Notes

- The exact rhythmic pattern of the count-in is implementation-defined
- ARR files describe the **mode**, not the note-level pattern
- The playback engine may ignore this directive if count-in is globally disabled

---

### 3.2 `#SECTION` (Section Label)

```
#SECTION <name> <start> <end>
```

Defines a **section label** over a contiguous range of chain entries.

- `<start>` and `<end>` are **1-based indices**, inclusive
- Sections are metadata only and do not affect playback order

Example:

```
#SECTION Verse 1 4
#SECTION Chorus 5 8
```

#### Compatibility Notes

- Parsers SHOULD accept both:
  - legacy 0-based definitions (`0 3`)
  - current 1-based definitions (`1 4`)
- If `<start>` is `0`, the definition MUST be treated as legacy 0-based

---

### 3.3 `#PLAY` (Song Structure Hint)

```
#PLAY <token> <token> ...
```

Provides a **human-readable summary** of the song structure.

- Tokens may be section names or pattern identifiers
- Informational only in v0.05
- Playback MUST NOT be driven by this line

Example:

```
#PLAY Verse Chorus Verse Ending
```

---

## 4. MAIN Playback Line

```
MAIN|<item>,<item>,...
```

Each item represents a playback instruction:

- `<n>` : play pattern pool index `n` once
- `<n>x<m>` : play pattern pool index `n`, repeated `m` times

Example:

```
MAIN|1x2,2,3x4
```

### Characteristics

- This line is the **authoritative playback definition**
- Pool indices are **1-based**
- Used directly by the APS playback engine

---

## 5. Section Semantics

In ARR v0.05:

- Sections are **labels**, not structural blocks
- Sections do not define loops or control flow
- Sections do not nest
- Overlapping sections are discouraged but not strictly forbidden

Sections exist to support:

- Visual grouping in the chain editor
- Human understanding of song form
- Future export into structured DSL formats

---

## 6. Editing and Saving Rules

### 6.1 Saving

APS writes ARR files in the following order:

1. `#COUNTIN` (if applicable)
2. All `#SECTION` definitions (1-based)
3. Optional `#PLAY` summary
4. The `MAIN|...` line

---

## 7. Compatibility and Forward Strategy

ARR v0.05 is **not a DSL**.

The following features are intentionally NOT supported:

- `[SECTION]:` blocks
- Grouping `( )*N`
- Symbolic references (`@1`, `@2`)

These features are reserved for ARR v0.1 and later.

---

## 8. Versioning Policy

- Files conforming to this document are considered **ARR v0.05**
- APS may treat files without explicit version tags as v0.05-compatible
- Future versions MUST NOT silently change the meaning of:
  - `#COUNTIN`
  - `#SECTION`
  - `MAIN|...`

---

## 9. Summary

ARR v0.05 is a **pragmatic, editor-friendly chain format**:

- Stable
- Human-readable
- Backward-compatible
- Forward-looking without overreach

It reflects what APS can reliably support today.

---

# Appendix A. ARR Load Semantics and Section Handling Policy (v0.05)

This appendix defines the policy for loading ARR files into APS
when an existing chain is already present in the editor.

---

## A.1 Problem Statement

Loading an ARR file may affect:

- Existing chain entries
- Section labels (start/end based)
- Cursor and selection state
- Unsaved modifications

ARR loading is therefore a **state-destructive operation** and requires explicit policy.

---

## A.2 Load Operation Types

### A.2.1 Replace (Full Replacement)

- Discards the existing chain entirely
- Replaces it with the loaded ARR content

**Characteristics**
- Safest and most predictable behavior
- Minimal implementation complexity
- Matches typical user expectations

---

### A.2.2 Append (Append to End)

- Appends the loaded ARR chain to the end of the current chain

**Required considerations**
- Apply index offsets to appended sections
- Resolve section name conflicts

---

### A.2.3 Insert (Insert at Cursor)

- Inserts the loaded ARR chain at the current cursor position

**Characteristics**
- Most powerful
- Most complex
- Requires advanced section conflict handling

---

## A.3 Handling Unsaved Modifications

If the current chain has unsaved changes:

- A warning dialog MUST be shown
- At minimum, the following options SHOULD be provided:
  - Replace
  - Cancel

---

## A.4 Section Handling (Label Model)

In ARR v0.05, sections are range-based labels.

### A.4.1 Append Case

- Section ranges MUST be offset by the current chain length
- Section name conflicts MUST be resolved

---

### A.4.2 Insert Inside a Section

If the insertion point lies inside an existing section, possible policies include:

- **Expand** (recommended): extend the section to include inserted content
- Split
- Keep-left / Keep-right
- Invalidate (remove section with warning)

ARR v0.05 RECOMMENDS the **Expand** policy.

---

## A.5 Section Name Conflicts

When section names collide:

- Duplicate names MAY be allowed
- **Automatic renaming** (e.g. `Verse` → `Verse_2`) is RECOMMENDED
- Merging sections is NOT recommended in v0.05
- Prompting the user is optional but discouraged

---

## A.6 Handling `#PLAY`

In ARR v0.05, `#PLAY` is informational only.

- Replace: MAY be preserved
- Append / Insert:
  - SHOULD be regenerated from the resulting chain and sections

---

## A.7 Recommended Minimal Policy (v0.05)

For ARR v0.05, APS SHOULD adopt the following default behavior:

1. Default load mode: **Replace only**
2. If unsaved changes exist:
   - Show warning
   - Options: Replace / Cancel
3. Append and Insert are deferred to future Import features

This policy minimizes complexity while preserving future extensibility.

---

## A.8 Conclusion

ARR loading is not merely file input,
but a **policy decision affecting the editor state model**.

ARR v0.05 deliberately adopts a conservative,
Replace-centered approach to ensure stability during active development.
