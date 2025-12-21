# aps_chainedit.py — chain editing logic for APS v0.27 + Undo hook
import curses
import copy
from typing import List, Callable, Optional, Tuple

from aps_core import ChainEntry
from aps_sections import ChainSelection, SectionManager

# ----------------------------------------------------------------------
# Stable module-level clipboard + last message
#   - avoids nonlocal/scope issues
#   - allows UI layer to show a persistent status line if it wants
# ----------------------------------------------------------------------
CHAIN_CLIPBOARD = {"entries": None, "mode": None}  # mode: "copy"|"cut"
CHAIN_LAST_MSG: str = ""

# ----------------------------------------------------------------------
# Section edit request (UI handled by aps_main; this module raises a request)
# ----------------------------------------------------------------------
CHAIN_UI_REQUEST = None  # dict or None

def pop_chain_ui_request():
    """Return and clear the pending UI request from chain editor."""
    global CHAIN_UI_REQUEST
    req = CHAIN_UI_REQUEST
    CHAIN_UI_REQUEST = None
    return req



def _set_msg(msg: str) -> None:
    global CHAIN_LAST_MSG
    CHAIN_LAST_MSG = msg


def _extract_selection_bounds(selection: ChainSelection) -> Optional[Tuple[int, int]]:
    """Best-effort bounds extractor for ChainSelection variations."""
    # Common attribute pairs used across versions
    attr_pairs = [
        ("start_idx", "end_idx"),
        ("start", "end"),
        ("sel_start", "sel_end"),
        ("begin_idx", "last_idx"),
        ("a", "b"),
        ("anchor", "cursor"),
    ]
    for a_name, b_name in attr_pairs:
        if hasattr(selection, a_name) and hasattr(selection, b_name):
            try:
                return int(getattr(selection, a_name)), int(getattr(selection, b_name))
            except Exception:
                pass

    # Common method names
    method_names = ["bounds", "get_bounds", "get_range", "range"]
    for m in method_names:
        if hasattr(selection, m) and callable(getattr(selection, m)):
            try:
                a, b = getattr(selection, m)()
                return int(a), int(b)
            except Exception:
                pass

    return None



def _get_section_range(section_mgr: SectionManager, name: str):
    """Best-effort section range getter; returns (a,b) inclusive or None."""
    for m in ("section_range", "get_section_range", "range_of", "get_range"):
        if hasattr(section_mgr, m) and callable(getattr(section_mgr, m)):
            try:
                a, b = getattr(section_mgr, m)(name)
                return int(a), int(b)
            except Exception:
                pass
    for attr in ("sections", "section_map", "ranges", "section_ranges"):
        if hasattr(section_mgr, attr):
            d = getattr(section_mgr, attr)
            if isinstance(d, dict) and name in d:
                v = d[name]
                if isinstance(v, (tuple, list)) and len(v) >= 2:
                    try:
                        return int(v[0]), int(v[1])
                    except Exception:
                        pass
                if isinstance(v, dict):
                    for ka, kb in (("start", "end"), ("a", "b"), ("from", "to")):
                        if ka in v and kb in v:
                            try:
                                return int(v[ka]), int(v[kb])
                            except Exception:
                                pass
    return None


def _find_section_at(section_mgr: SectionManager, chain: List[ChainEntry], idx: int) -> Optional[str]:
    """Return the section name that contains idx, or None."""
    try:
        names = section_mgr.list_sections()
    except Exception:
        return None
    for name in names:
        r = _get_section_range(section_mgr, name)
        if not r:
            continue
        a, b = r
        if a <= idx <= b:
            return name
    return None


def _remove_section(section_mgr: SectionManager, name: str) -> bool:
    """Best-effort section removal."""
    for m in ("remove_section", "delete_section", "del_section", "unset_section", "drop_section"):
        if hasattr(section_mgr, m) and callable(getattr(section_mgr, m)):
            try:
                getattr(section_mgr, m)(name)
                return True
            except Exception:
                return False
    for attr in ("sections", "section_map", "ranges", "section_ranges"):
        if hasattr(section_mgr, attr):
            d = getattr(section_mgr, attr)
            if isinstance(d, dict) and name in d:
                try:
                    del d[name]
                    return True
                except Exception:
                    return False
    return False


def remove_section_by_name(section_mgr: SectionManager, name: str) -> bool:
    """UI helper: remove a section by name."""
    return _remove_section(section_mgr, name)


def section_name_exists(section_mgr: SectionManager, name: str) -> bool:
    """UI helper: check duplicate section name."""
    try:
        return name in section_mgr.list_sections()
    except Exception:
        return False


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

      블록 Copy/Cut/Paste
      - C : 선택 블록 복사 (선택 없으면 현재 줄 1개)
      - X : 선택 블록 잘라내기
      - P : 클립보드 붙여넣기 (현재 줄 뒤)

    push_undo()가 주어지면, 실제 편집이 일어나기 직전에 호출되어
    Undo 스택에 이전 상태가 저장된다.
    """
    if not chain:
        return chain_selected_idx, False

    total = len(chain)
    updated = False

    def _undo_before_edit():
        if push_undo is not None:
            push_undo()

    def _get_block_range() -> Tuple[int, int]:
        """Return (a,b) inclusive; if no active selection, returns (cursor,cursor)."""
        n = len(chain)
        if n <= 0:
            return 0, 0

        if not getattr(selection, "selection_active", False):
            idx = max(0, min(chain_selected_idx, n - 1))
            return idx, idx

        bounds = _extract_selection_bounds(selection)
        if not bounds:
            idx = max(0, min(chain_selected_idx, n - 1))
            return idx, idx

        a, b = bounds
        if a > b:
            a, b = b, a
        a = max(0, min(a, n - 1))
        b = max(0, min(b, n - 1))
        return a, b

    def _shift_after_delete(start_idx: int, count: int) -> None:
        # SectionManager API varies; keep best-effort and non-fatal.
        for m in ("shift_after_delete", "shift_after_remove", "shift_after_del"):
            if hasattr(section_mgr, m) and callable(getattr(section_mgr, m)):
                try:
                    getattr(section_mgr, m)(start_idx, count)
                    return
                except Exception:
                    return

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
        _set_msg("block select")
        return chain_selected_idx, True

    # E/e: 섹션명 편집(삭제) 요청
    # - UI(대화상자)는 aps_main에서 처리하고, 여기서는 요청만 올린다.
    # - 리네임은 "삭제 후 s로 새로 생성" 정책을 따른다.
    if ch in (ord("R"), ord("r")):
        global CHAIN_UI_REQUEST
        cur_sec = _find_section_at(section_mgr, chain, chain_selected_idx)
        try:
            all_secs = section_mgr.list_sections()
        except Exception:
            all_secs = []
        CHAIN_UI_REQUEST = {
            "type": "section_edit",
            "cursor_idx": chain_selected_idx,
            "current": cur_sec,
            "sections": list(all_secs),
        }
        _set_msg("section edit")
        return chain_selected_idx, True


    # --------------------------------------------------------------
    # Copy / Cut / Paste (C / X / P)
    # --------------------------------------------------------------
    if ch in (ord("C"), ord("c")):
        a, b = _get_block_range()
        CHAIN_CLIPBOARD["entries"] = copy.deepcopy(chain[a : b + 1])
        CHAIN_CLIPBOARD["mode"] = "copy"
        selection.reset()  # UX: copy clears highlight
        _set_msg(f"copied {b - a + 1} item(s)")
        return chain_selected_idx, True

    if ch in (ord("X"), ord("x")):
        a, b = _get_block_range()
        _undo_before_edit()
        CHAIN_CLIPBOARD["entries"] = copy.deepcopy(chain[a : b + 1])
        CHAIN_CLIPBOARD["mode"] = "cut"
        del chain[a : b + 1]
        _shift_after_delete(a, b - a + 1)
        chain_selected_idx = min(a, len(chain) - 1) if chain else 0
        selection.reset()
        _set_msg(f"cut {b - a + 1} item(s)")
        return chain_selected_idx, True

    if ch in (ord("P"), ord("p")):
        entries = CHAIN_CLIPBOARD.get("entries")
        if not entries:
            _set_msg("nothing to paste")
            return chain_selected_idx, False

        _undo_before_edit()
        insert_at = min(chain_selected_idx + 1, len(chain))
        chain[insert_at:insert_at] = copy.deepcopy(entries)
        section_mgr.shift_after_insert(insert_at, len(entries))
        chain_selected_idx = insert_at + len(entries) - 1
        selection.reset()

        n = len(entries)
        if CHAIN_CLIPBOARD.get("mode") == "cut":
            CHAIN_CLIPBOARD["entries"] = None
            CHAIN_CLIPBOARD["mode"] = None
        _set_msg(f"pasted {n} item(s)")
        return chain_selected_idx, True

    # '-' : 반복 감소 (N>1이면 N-1, N=1이면 줄 삭제)
    if ch == ord("-"):
        _undo_before_edit()
        entry = chain[chain_selected_idx]
        if entry.repeats > 1:
            entry.repeats -= 1
        else:
            del chain[chain_selected_idx]
            _shift_after_delete(chain_selected_idx, 1)
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
            _shift_after_delete(chain_selected_idx, 1)
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
            _shift_after_delete(chain_selected_idx - 1, 1)
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
