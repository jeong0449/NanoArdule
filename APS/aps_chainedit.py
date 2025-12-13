# aps_chainedit.py — chain editing logic for APS v0.27 + Undo hook
import curses
from typing import List, Callable, Optional

from aps_core import ChainEntry
from aps_sections import ChainSelection, SectionManager


def handle_chain_keys(
    ch,
    chain: List[ChainEntry],
    chain_selected_idx: int,
    selection: ChainSelection,
    section_mgr: SectionManager,
    files: List[str],
    selected_pattern_idx: int,
    push_undo: Optional[Callable[[], None]] = None,
):
    """
    체인 편집 기능:

      이동 / 선택
      - ↑/↓/Home/End/PgUp/PgDn 이동
      - V: 블록 선택 시작
      - KEY_SR/KEY_SF: (지원되는 터미널에서) Shift+Up/Down 블록 확장

      반복/삭제/삽입
      - - : 현재 줄 xN 감소 (N>1이면 N-1, N=1이면 줄 삭제)
      - + : 현재 줄 xN 증가
      - Delete(KEY_DC) : 현재 줄 xN 감소 (N>1) / N=1이면 줄 삭제
      - Backspace : 하이라이트 직전 줄 삭제
      - Enter : 현재 줄 뒤에 패턴 삽입 (파일은 files[selected_pattern_idx])
      - O : 현재 줄 앞에 패턴 삽입
      - o : 첫 번째 섹션을 현재 줄 뒤에 삽입

    push_undo()가 주어지면, 실제 편집이 일어나기 직전에 호출되어
    Undo 스택에 이전 상태가 저장된다.
    """
    if not chain:
        return chain_selected_idx, False

    total = len(chain)
    updated = False

    def _undo_before_edit():
        nonlocal push_undo
        if push_undo is not None:
            push_undo()

    # 일부 터미널에서 지원되는 Shift+Up/Down
    if ch == curses.KEY_SR:  # Shift+Up
        if not selection.selection_active:
            selection.begin(chain_selected_idx)
        if chain_selected_idx > 0:
            chain_selected_idx -= 1
            selection.extend(chain_selected_idx)
        return chain_selected_idx, True

    if ch == curses.KEY_SF:  # Shift+Down
        if not selection.selection_active:
            selection.begin(chain_selected_idx)
        if chain_selected_idx < total - 1:
            chain_selected_idx += 1
            selection.extend(chain_selected_idx)
        return chain_selected_idx, True

    # 기본 ↑/↓ 이동
    if ch in (curses.KEY_UP, ord("k")):
        if chain_selected_idx > 0:
            chain_selected_idx -= 1
            if selection.selection_active:
                selection.extend(chain_selected_idx)
        return chain_selected_idx, True

    if ch in (curses.KEY_DOWN, ord("j")):
        if chain_selected_idx < total - 1:
            chain_selected_idx += 1
            if selection.selection_active:
                selection.extend(chain_selected_idx)
        return chain_selected_idx, True

    # Home / End / PgUp / PgDn
    if ch == curses.KEY_HOME:
        chain_selected_idx = 0
        return chain_selected_idx, True

    if ch == curses.KEY_END:
        chain_selected_idx = len(chain) - 1
        return chain_selected_idx, True

    if ch == curses.KEY_PPAGE:
        chain_selected_idx = max(0, chain_selected_idx - 10)
        return chain_selected_idx, True

    if ch == curses.KEY_NPAGE:
        chain_selected_idx = min(len(chain) - 1, chain_selected_idx + 10)
        return chain_selected_idx, True

    # V/v: 블록 선택 시작 (단순 선택은 Undo 대상 아님)
    if ch in (ord("V"), ord("v")):
        selection.begin(chain_selected_idx)
        return chain_selected_idx, True

    # '-' : 반복 감소 (N>1이면 N-1, N=1이면 줄 삭제)
    if ch == ord("-"):
        _undo_before_edit()
        entry = chain[chain_selected_idx]
        if entry.repeats > 1:
            entry.repeats -= 1
        else:
            del chain[chain_selected_idx]
            if chain:
                if chain_selected_idx >= len(chain):
                    chain_selected_idx = len(chain) - 1
            else:
                chain_selected_idx = 0
        selection.reset()
        return chain_selected_idx, True

    # '+' : 반복 증가
    if ch == ord("+"):
        _undo_before_edit()
        chain[chain_selected_idx].repeats += 1
        return chain_selected_idx, True

    # Delete(KEY_DC) : 현재 줄 xN 감소 / N=1이면 줄 삭제
    if ch == curses.KEY_DC:
        _undo_before_edit()
        entry = chain[chain_selected_idx]
        if entry.repeats > 1:
            entry.repeats -= 1
        else:
            del chain[chain_selected_idx]
            if chain:
                if chain_selected_idx >= len(chain):
                    chain_selected_idx = len(chain) - 1
            else:
                chain_selected_idx = 0
        selection.reset()
        return chain_selected_idx, True

    # Backspace : 하이라이트 직전 줄 삭제
    # 터미널에 따라 BACKSPACE는 KEY_BACKSPACE, 127, 8 등으로 들어올 수 있음
    if ch in (curses.KEY_BACKSPACE, 127, 8):
        if chain_selected_idx > 0:
            _undo_before_edit()
            del chain[chain_selected_idx - 1]
            chain_selected_idx -= 1
            selection.reset()
            return chain_selected_idx, True

    # Enter: insert-after (현재 위치 뒤)
    if ch in (10, 13):
        if not files:
            return chain_selected_idx, False
        _undo_before_edit()
        fn = files[selected_pattern_idx]
        insert_at = chain_selected_idx + 1
        chain.insert(insert_at, ChainEntry(fn, 1))
        section_mgr.shift_after_insert(insert_at, 1)
        chain_selected_idx = insert_at
        selection.reset()
        return chain_selected_idx, True

    # O: insert-before (현재 위치 앞)
    if ch == ord("O"):
        if not files:
            return chain_selected_idx, False
        _undo_before_edit()
        fn = files[selected_pattern_idx]
        insert_at = chain_selected_idx
        chain.insert(insert_at, ChainEntry(fn, 1))
        section_mgr.shift_after_insert(insert_at, 1)
        chain_selected_idx = insert_at
        selection.reset()
        return chain_selected_idx, True

    # o: 첫 번째 섹션을 현재 위치 뒤에 삽입
    if ch == ord("o"):
        names = section_mgr.list_sections()
        if not names:
            return chain_selected_idx, False
        secname = names[0]
        sec_entries = section_mgr.section_entries(chain, secname)
        if sec_entries:
            _undo_before_edit()
            insert_at = chain_selected_idx + 1
            for i, e in enumerate(sec_entries):
                chain.insert(insert_at + i, e)
            section_mgr.shift_after_insert(insert_at, len(sec_entries))
            chain_selected_idx = insert_at
            selection.reset()
            return chain_selected_idx, True

    return chain_selected_idx, updated
