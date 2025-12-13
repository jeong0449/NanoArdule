# aps_sections.py — selection & section manager for APS v0.27
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple

from aps_core import ChainEntry


class ChainSelection:
    def __init__(self):
        self.selection_active: bool = False
        self.start: Optional[int] = None
        self.end: Optional[int] = None

    def reset(self):
        self.selection_active = False
        self.start = None
        self.end = None

    def begin(self, idx: int):
        self.selection_active = True
        self.start = idx
        self.end = idx

    def extend(self, idx: int):
        if not self.selection_active:
            self.begin(idx)
            return
        self.end = idx
        if self.start is not None and self.end < self.start:
            self.start, self.end = self.end, self.start

    def get_range(self):
        if not self.selection_active:
            return None
        if self.start is None or self.end is None:
            return None
        return (self.start, self.end)


class SectionManager:
    def __init__(self):
        # name -> (start, end)
        self.sections: Dict[str, Tuple[int, int]] = {}

    def add_section(self, name: str, start: int, end: int) -> bool:
        if start > end:
            start, end = end, start
        if name in self.sections:
            return False
        for (s, e) in self.sections.values():
            if not (end < s or start > e):
                return False
        self.sections[name] = (start, end)
        return True

    def remove_section(self, name: str):
        self.sections.pop(name, None)

    def find_section(self, name: str):
        return self.sections.get(name)

    def get_section_range(self, name: str):
        """Return (start, end) tuple for a section name, or None."""
        return self.sections.get(name)


    def list_sections(self):
        return list(self.sections.keys())

    def section_entries(self, chain: List[ChainEntry], name: str):
        rng = self.find_section(name)
        if not rng:
            return None
        start, end = rng
        return [ChainEntry(e.filename, e.repeats, e.section) for e in chain[start:end+1]]

    def shift_after_insert(self, insert_at: int, amount: int):
        new = {}
        for name, (s, e) in self.sections.items():
            if s >= insert_at:
                s += amount
            if e >= insert_at:
                e += amount
            new[name] = (s, e)
        self.sections = new

    def shift_after_delete(self, delete_start: int, delete_end: int):
        delete_count = delete_end - delete_start + 1
        new_sections = {}
        for name, (s, e) in self.sections.items():
            if not (e < delete_start or s > delete_end):
                continue
            if s > delete_end:
                s -= delete_count
            if e > delete_end:
                e -= delete_count
            new_sections[name] = (s, e)
        self.sections = new_sections
