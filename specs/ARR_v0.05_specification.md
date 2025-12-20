# ARR v0.05 Specification
**Ardule Chain File – Transitional Specification**

---

## 1. Purpose

ARR v0.05 is a **transitional, human-readable chain format** used by APS (Ardule Pattern Studio) to describe the playback order of drum patterns.

This version intentionally:

- Treats **sections as labels (metadata)**, not structural elements
- Preserves compatibility with the existing chain editor and playback engine
- Serves as a bridge toward a future ARR DSL (e.g. v0.1), without enforcing it

ARR v0.05 files are designed to be:

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

Additional modes (e.g. `CountIn_SD`, `CountIn_RIM`) may be supported by APS implementations but are not required by this specification.

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

- Parsers should accept both:
  - legacy 0-based definitions (`0 3`)
  - current 1-based definitions (`1 4`)
- If `<start>` is `0`, the definition is treated as legacy 0-based

---

### 3.3 `#PLAY` (Song Structure Hint)

```
#PLAY <token> <token> ...
```

Provides a **human-readable summary** of the song structure.

- Tokens may be section names or pattern identifiers
- Informational only in v0.05
- Playback is not driven by this line

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
- They do not define loops or control flow
- Overlapping sections are discouraged but not strictly forbidden

Sections exist to support:

- Visual grouping in the chain editor
- Human understanding of song form
- Future export into structured DSL formats

---

## 6. Editing and Loading Rules

### 6.1 Loading

- APS may clear existing chain state (Replace)
- Or import / append (implementation-dependent)
- Section labels should be restored if present

### 6.2 Saving

APS writes, in order:

1. `#COUNTIN` (if applicable)
2. All `#SECTION` definitions (1-based)
3. Optional `#PLAY` summary
4. The `MAIN|...` line

---

## 7. Compatibility and Forward Strategy

ARR v0.05 is **not a DSL**.

The following are intentionally not supported:

- `[SECTION]:` blocks
- Grouping `( )*N`
- Symbolic references (`@1`, `@2`)

These features are reserved for ARR v0.1+.

---

## 8. Versioning Policy

- Files conforming to this document are considered **ARR v0.05**
- APS may treat files without explicit version tags as v0.05-compatible
- Future versions must not silently change the meaning of:
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

# Appendix A. ARR Load Semantics and Section Handling Policy

# ARR 로드 동작 및 섹션 처리 정책 (v0.05)

이 문서는 **APS(Ardule Pattern Studio)** 체인 에디터에서  
이미 체인이 존재하는 상태에서 **ARR 파일을 로드할 때의 동작 정책**을 정리한 것이다.

본 문서는 **ARR v0.05 (섹션 = 라벨)** 모델을 전제로 하며,  
향후 ARR v0.1 이상의 구조적 DSL 도입을 위한 *의사결정 기록*의 성격을 가진다.

---

## 1. 문제 정의

체인 편집기에서 ARR을 로드할 때, 이미 다음과 같은 상태가 존재할 수 있다.

- 기존 체인 항목
- 섹션 라벨(start/end 기반)
- 커서 위치 및 선택 상태
- 저장되지 않은 수정 내용(modified state)

ARR 로드는 단순한 파일 I/O가 아니라  
**편집기 상태 전체에 영향을 주는 파괴적 연산**이 될 수 있으므로  
명확한 정책 정의가 필요하다.

---

## 2. ARR 로드 동작의 기본 유형

APS에서 고려할 수 있는 ARR 로드 동작은 크게 세 가지이다.

### 2.1 Replace (전체 교체)

- 기존 체인을 모두 삭제
- ARR 파일의 내용으로 완전히 교체

**특징**
- 가장 단순하고 안전함
- 사용자 기대와 일치
- 구현 난이도 최소

---

### 2.2 Append (뒤에 추가)

- 기존 체인 뒤에 ARR 체인을 이어붙임

**필요 고려사항**
- 기존 체인 길이만큼 인덱스 오프셋 적용
- 섹션 start/end 이동
- 섹션 이름 충돌 가능성

---

### 2.3 Insert (중간 삽입)

- 현재 커서 위치를 기준으로 체인 중간에 삽입

**특징**
- 가장 강력하지만 가장 복잡
- 섹션 충돌 및 재계산 문제 발생

---

## 3. 수정 상태(modified)에 대한 처리

ARR 로드 시 기존 체인에 저장되지 않은 변경이 있는 경우:

- 최소한 **경고 메시지**는 반드시 필요
- 선택지 예:
  - Replace (기존 내용 폐기)
  - Cancel (로드 취소)
  - (선택적) Save first → Replace

ARR v0.05 단계에서는 **Replace / Cancel**만 제공하는 것이 바람직하다.

---

## 4. 섹션이 라벨일 때 발생하는 핵심 문제

ARR v0.05에서 섹션은 구조가 아닌 **범위 라벨(start/end)** 이다.

### 4.1 Append 시 섹션 처리

- 로드된 섹션은 기존 체인 길이만큼 start/end 오프셋 적용
- 섹션 이름 충돌 시 별도 정책 필요

---

### 4.2 Insert 시 섹션 내부 삽입 문제

삽입 지점이 기존 섹션 내부에 포함되는 경우 다음 선택지가 존재한다.

- **Expand**  
  기존 섹션의 end를 삽입 길이만큼 확장 (가장 직관적)
- Split  
  섹션을 둘로 분할
- Keep-left / Keep-right  
  한쪽만 유지
- Invalidate  
  섹션 해제 및 경고

ARR v0.05 단계에서는 **Expand 정책이 가장 안전**하다.

---

## 5. 섹션 이름 충돌 정책

Append / Insert 시 로드한 ARR의 섹션 이름이 기존 섹션과 충돌할 수 있다.

가능한 정책:

- 중복 허용
- **자동 리네임 (권장)**  
  예: `Verse` → `Verse_2`
- 병합
- 사용자에게 매번 질의

ARR v0.05 단계에서는 **자동 리네임**이 가장 현실적이다.

---

## 6. `#PLAY` (Song Structure Hint) 처리

ARR v0.05에서 `#PLAY`는 **정보성 주석**이다.

- Replace: 그대로 유지 가능
- Append / Insert:
  - 무시
  - 뒤에 이어붙이기
  - **체인/섹션 상태 기준으로 재생성 (권장)**

---

## 7. 권장 최소 정책 (ARR v0.05 기준)

현 단계에서 APS에 권장되는 정책은 다음과 같다.

1. 기본 ARR 로드 동작은 **Replace only**
2. 기존 체인이 비어있지 않고 수정 상태라면 경고 표시
3. 사용자 선택:
   - Replace
   - Cancel
4. Append / Insert는 **향후 Import 기능으로 분리**
5. 섹션 충돌/이름 충돌 문제는 당장 다루지 않음

이 정책은:
- 구현 복잡도를 최소화하고
- 섹션 모델을 안정화하며
- 향후 ARR v0.1 DSL로의 이행을 방해하지 않는다.

---

## 8. 결론

ARR 로드는 단순한 파일 읽기가 아니라  
**편집기 상태 모델에 대한 정책적 선택의 집합**이다.

ARR v0.05 단계에서는:

- Replace 중심의 보수적 정책을 채택하고
- 고급 병합/삽입 기능은 후속 단계로 미룬다

이 문서는 그 결정을 명시적으로 기록하기 위한 것이다.
