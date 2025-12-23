# ARR v0.05 Specification

**Ardule Chain File – Transitional Specification (Revised)**

---

## 1. Purpose

ARR v0.05 is a **transitional, human-readable chain format** used by APS (Ardule Pattern Studio)
to describe the playback order of drum patterns.

This version intentionally:

* Treats **sections as labels (metadata)**, not structural elements
* Preserves compatibility with the existing chain editor and playback engine
* Serves as a stable bridge toward a future ARR DSL (e.g. v0.1), without enforcing it

ARR v0.05 is designed to be:

* Easy to read and review by humans
* Safely editable by APS without complex parsing logic
* Backward-compatible during iterative development

---

## 2. File Structure Overview

An ARR v0.05 file consists of:

1. Optional comment / metadata lines (starting with `#`)
2. A **Pattern Pool** section (required if playback uses numeric references)
3. A single `MAIN|...` playback line (authoritative)

Example:

```
#COUNTIN CountIn_HH
#SECTION verse 1 4
#SECTION chorus 9 12
#PLAY
verse
5
6
7
8
chorus
13
14
15
16
#ENDPLAY
#APS ARR v0.05

BPM=120

1=BAL_P001.ADT
2=BAL_P002.ADT
3=BAL_P003.ADT
4=BAL_P004.ADT
5=BAL_P005.ADT
6=BAL_P006.ADT
7=BAL_P007.ADT
8=BAL_P008.ADT
9=FNK_P001.ADT
10=FNK_P002.ADT
11=FNK_P003.ADT
12=FNK_P004.ADT
13=POP_P001.ADT
14=POP_P002.ADT
15=POP_P003.ADT
16=POP_P004.ADT

MAIN|1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16

```

---

## 3. Comment and Metadata Lines

All metadata lines begin with `#` and are ignored by the playback engine unless explicitly stated.

### 3.1 `#COUNTIN` (Count-in Mode)

```
#COUNTIN <mode>
```

Defines the count-in behavior before playback starts.

Supported modes (v0.05):

* `CountIn_HH`
  Hi-hat based count-in (default APS behavior)
* `OFF`
  No count-in

Additional modes may be supported by implementations but are not required.

---

### 3.2 `#SECTION` (Section Label)

```
#SECTION <name> <start> <end>
```

Defines a **section label** over a contiguous range of playback steps.

* `<start>` and `<end>` are **1-based indices**, inclusive
* Indices refer to positions in the `MAIN|...` playback sequence
* Sections are metadata only and do not affect playback order

Example:

```
#SECTION Verse 1 4
#SECTION Chorus 5 8
```

Legacy note:

* Older ARR files MAY contain 0-based section indices
* APS SHOULD interpret such files as legacy input only

---

### 3.3 `#PLAY` (Song Structure Hint)

```
#PLAY <token> <token> ...
```

Provides a **human-readable summary** of the song structure.

* Tokens may be section names or symbolic labels
* Informational only in v0.05
* Playback MUST NOT be driven by this line

---

## 4. Pattern Pool (Required)

The Pattern Pool defines the mapping between numeric identifiers and ADT pattern files.

Each Pattern Pool entry associates a **1-based integer identifier** with a pattern file.

### 4.1 Syntax

```
N=FILENAME.ADT
```

* `N` is a positive integer starting from **1**
* `FILENAME.ADT` is the name of an ADT pattern file

### 4.2 Semantics

* Pattern Pool indices are **1-based** and human-oriented
* Numeric references in `MAIN|...` MUST refer to Pattern Pool indices
* The Pattern Pool provides the reference table for playback

### 4.3 Ordering and Uniqueness

* Entries SHOULD be contiguous (`1..K`) with no gaps
* Each index MUST appear at most once
* Duplicate filenames MAY appear, but APS SHOULD emit a de-duplicated pool

### 4.4 Requiredness

* If `MAIN|...` contains numeric references, a Pattern Pool **MUST be present**
* ARR files lacking a Pattern Pool while using numeric playback references are invalid

---

## 5. MAIN Playback Line

```
MAIN|<item>,<item>,...
```

Each item represents a playback instruction:

* `<n>` : play Pattern Pool index `n` once
* `<n>x<m>` : play Pattern Pool index `n`, repeated `m` times

Example:

```
MAIN|1x2,2,3x4
```

Characteristics:

* The `MAIN|...` line is the **single authoritative playback definition**
* All indices are **1-based Pattern Pool identifiers**

---

## 6. Section Semantics

In ARR v0.05:

* Sections are labels, not control structures
* Sections do not define loops or branching
* Sections do not nest

They exist to support:

* Visual grouping in the chain editor
* Human understanding of song form
* Future export to structured DSL formats

---

## 7. Editing and Saving Rules

APS writes ARR files in the following order:

1. `#COUNTIN` (if applicable)
2. All `#SECTION` definitions (1-based)
3. Optional `#PLAY` summary
4. Pattern Pool entries (`N=FILENAME.ADT`)
5. The `MAIN|...` playback line

---

## 8. Compatibility and Forward Strategy

ARR v0.05 is **not a DSL**.

The following features are intentionally not supported:

* Block-based sections
* Loop expressions
* Symbolic playback references

These are reserved for ARR v0.1 and later.

---

## 9. Versioning Policy

* Files conforming to this document are **ARR v0.05**
* APS MAY treat files without explicit version tags as v0.05-compatible
* Future versions MUST NOT silently change the meaning of:

  * `#COUNTIN`
  * `#SECTION`
  * `MAIN|...`

---

## 10. Summary

ARR v0.05 is a pragmatic, editor-friendly chain format:

* Human-readable
* 1-based indexing throughout
* Clear separation between Pattern Pool and playback timeline
* Stable for current APS use while enabling future evolution

---
