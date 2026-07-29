#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adc_rhythm_analysis.py 260729a

Shared grace/flam/ghost and straight/8T/16T subdivision analysis for ADC Toolkit.
Used by adc-patternlab.py and adc-mid2report.py.

The module analyzes MIDI data only; it does not render output or modify MIDI files.
Legacy adc_flam.py and adc_subdivision.py remain unchanged during migration stage 1.
"""
from __future__ import annotations

from collections import defaultdict
from statistics import median
from typing import Any, Iterable

from mido import Message, MidiFile

SCRIPT_NAME = "adc_rhythm_analysis.py"
VERSION = "260729a"
VERSION_TEXT = f"{SCRIPT_NAME} {VERSION}"

ADT_DRUM_FAMILIES = {
    35: "KK", 36: "KK", 37: "SS", 38: "SN", 40: "SN", 39: "CL",
    41: "LT", 43: "LT", 45: "MT", 47: "MT", 48: "HT", 50: "HT",
    42: "CH", 44: "PH", 46: "OH", 49: "CR", 52: "CR", 55: "CR", 57: "CR",
    51: "RD", 53: "RD", 59: "RD",
}
GHOST_FAMILIES = {"SN", "SS", "LT", "MT", "HT", "CL"}


def _get(event: Any, name: str, default=None):
    if isinstance(event, dict):
        return event.get(name, default)
    return getattr(event, name, default)


def gather_note_on_ticks(mid: MidiFile, excluded_ticks: set[int] | None = None) -> list[int]:
    """Collect absolute note-on ticks, preferring channel 10 when present."""
    excluded_ticks = excluded_ticks or set()
    all_ticks: list[int] = []
    drum_ticks: list[int] = []
    for track in mid.tracks:
        tick = 0
        for msg in track:
            tick += msg.time
            if isinstance(msg, Message) and msg.type == "note_on" and msg.velocity > 0:
                if tick in excluded_ticks:
                    continue
                all_ticks.append(tick)
                if getattr(msg, "channel", -1) == 9:
                    drum_ticks.append(tick)
    return sorted(drum_ticks if drum_ticks else all_ticks)


def classify_subdivision(tpq: int, note_ticks: Iterable[int]) -> dict:
    """Classify straight, 8T, or 16T evidence without overcalling 16T.

    Beat anchors and the shared half-beat are excluded. A 16T result requires
    dominant evidence at both exclusive 1/6 and 5/6 phases.
    """
    if tpq <= 0:
        tpq = 1
    tol = max(1, tpq // 24)
    anchor = shared_half = straight = t8 = t16 = unclassified = 0
    t8_phase = [0, 0]
    t16_phase = [0, 0]

    for tick in sorted(set(int(t) for t in note_ticks)):
        phase = tick % tpq
        d_anchor = min(abs(phase), abs(tpq - phase))
        d_half = abs(phase - tpq / 2)
        d_straight = min(abs(phase - tpq / 4), abs(phase - 3 * tpq / 4))
        d8a, d8b = abs(phase - tpq / 3), abs(phase - 2 * tpq / 3)
        d16a, d16b = abs(phase - tpq / 6), abs(phase - 5 * tpq / 6)
        if d_anchor <= tol:
            anchor += 1
        elif d_half <= tol:
            shared_half += 1
        else:
            distance, kind, phase_index = min(
                [(d_straight, "straight", -1), (d8a, "8T", 0), (d8b, "8T", 1),
                 (d16a, "16T", 0), (d16b, "16T", 1)],
                key=lambda item: item[0],
            )
            if distance > tol:
                unclassified += 1
            elif kind == "straight":
                straight += 1
            elif kind == "8T":
                t8 += 1
                t8_phase[phase_index] += 1
            else:
                t16 += 1
                t16_phase[phase_index] += 1

    triplet = t8 + t16
    evidence = straight + triplet
    straight_ratio = straight / evidence if evidence else 0.0
    triplet_ratio = triplet / evidence if evidence else 0.0
    grid = resolution = subdivision = rhythmic_feel = "unknown"

    if evidence:
        if straight >= 2 and straight_ratio >= 0.60:
            grid, resolution, subdivision, rhythmic_feel = "straight", "16", "straight-16", "straight"
        elif triplet >= 2 and triplet_ratio >= 0.60:
            strong_16 = (
                t16 >= 4 and t16 / evidence >= 0.60 and
                t16 / max(1, triplet) >= 0.67 and min(t16_phase) >= 1
            )
            strong_8 = t8 >= 2 and t8 / max(1, triplet) >= 0.60
            grid, rhythmic_feel = "triplet", "shuffle/swing"
            if strong_16:
                resolution, subdivision = "16T", "triplet-16T"
            elif strong_8:
                resolution, subdivision = "8T", "triplet-8T"
            else:
                resolution, subdivision = "ambiguous", "triplet-ambiguous"
        else:
            grid = resolution = subdivision = "mixed"
            rhythmic_feel = "mixed/ambiguous"

    details = {
        "samples": evidence,
        "anchor": anchor,
        "anchor_hits": anchor,
        "shared_half": shared_half,
        "shared_half_hits": shared_half,
        "straight": straight,
        "straight_hits": straight,
        "8T": t8,
        "8T_phase": t8_phase,
        "triplet_8t_hits": t8,
        "16T": t16,
        "16T_phase": t16_phase,
        "triplet_16t_only_hits": t16,
        "triplet_hits": triplet,
        "unclassified": unclassified,
        "unclassified_hits": unclassified,
        "tol": tol,
        "tol_ticks": tol,
    }
    return {
        "grid": grid,
        "resolution": resolution,
        "subdivision": subdivision,
        "rhythmic_feel": rhythmic_feel,
        "confidence": round(max(straight_ratio, triplet_ratio) if evidence else 0.0, 3),
        "straight": round(straight_ratio, 3),
        "triplet": round(triplet_ratio, 3),
        "straight_hit_ratio": round(straight_ratio, 3),
        "triplet_hit_ratio": round(triplet_ratio, 3),
        "details": details,
    }


def triplet_vs_straight_score(tpq: int, note_ticks: list[int]) -> dict:
    """Backward-compatible public name for the shared classifier."""
    return classify_subdivision(tpq, note_ticks)


def tick_to_bar_position(tick: int, tpq: int, ts_segs: list):
    """Map an absolute tick to a 1-based bar, beat, and meter."""
    bars_before = 0
    for t0, t1, (num, den) in ts_segs:
        bar_ticks = tpq * 4.0 * num / den
        if bar_ticks <= 0:
            continue
        if tick >= t1:
            bars_before += int((t1 - t0) // bar_ticks)
            continue
        if tick >= t0:
            rel = tick - t0
            bar_in_seg = int(rel // bar_ticks)
            tick_in_bar = rel - bar_in_seg * bar_ticks
            beat_ticks = tpq * 4.0 / den
            beat = tick_in_bar / beat_ticks + 1.0
            return bars_before + bar_in_seg + 1, beat, (num, den)
    return bars_before + 1, 1.0, ts_segs[-1][2] if ts_segs else (4, 4)


def analyze_triplet_by_bar(note_ticks: list[int], tpq: int, ts_segs: list) -> list[dict]:
    ticks_by_bar: dict[int, list[int]] = defaultdict(list)
    bar_meter = {}
    for tick in note_ticks:
        bar, _beat, meter = tick_to_bar_position(tick, tpq, ts_segs)
        ticks_by_bar[bar].append(tick)
        bar_meter[bar] = meter
    results = []
    for bar in sorted(ticks_by_bar):
        ticks = sorted(set(ticks_by_bar[bar]))
        score = classify_subdivision(tpq, ticks)
        det = score["details"]
        results.append({
            "bar": bar,
            "meter": bar_meter.get(bar, (4, 4)),
            "note_positions": len(ticks),
            "samples": det["samples"],
            "anchor_hits": det["anchor_hits"],
            "shared_half_hits": det["shared_half_hits"],
            "straight_hits": det["straight_hits"],
            "triplet_hits": det["triplet_hits"],
            "triplet_8t_hits": det["triplet_8t_hits"],
            "triplet_16t_only_hits": det["triplet_16t_only_hits"],
            "triplet_hit_ratio": score["triplet_hit_ratio"],
            "straight_hit_ratio": score["straight_hit_ratio"],
            "grid": score["grid"],
            "resolution": score["resolution"],
            "subdivision": score["subdivision"],
            "triplet_candidate": score["grid"] == "triplet",
            "tol_ticks": det["tol_ticks"],
        })
    return results


def recommended_steps_per_bar(numerator: int, denominator: int, decision=None) -> int:
    if (numerator, denominator) == (4, 4):
        steps = 16
    elif (numerator, denominator) in ((3, 4), (6, 8)):
        steps = 12
    else:
        steps = max(8, 4 * numerator)
    if decision and decision.get("grid") == "triplet" and (numerator, denominator) == (4, 4):
        steps = 24
    return int(steps)


def collect_drum_note_events(mid: MidiFile) -> list[dict]:
    """Return channel-10 note-on events as absolute-tick dictionaries."""
    out = []
    for track_index, track in enumerate(mid.tracks):
        tick = 0
        for msg in track:
            tick += msg.time
            if (isinstance(msg, Message) and msg.type == "note_on" and
                    msg.velocity > 0 and getattr(msg, "channel", -1) == 9):
                out.append({
                    "tick": tick, "note": int(msg.note), "velocity": int(msg.velocity),
                    "family": ADT_DRUM_FAMILIES.get(int(msg.note), f"N{int(msg.note)}"),
                    "track": track_index,
                })
    out.sort(key=lambda e: (e["tick"], e["track"], e["note"]))
    return out


def detect_flams(events: Iterable[Any], tpq: int) -> dict:
    """Detect conservative grace/main flam candidates by ADT drum family."""
    normalized = []
    for index, event in enumerate(events):
        note = int(_get(event, "note", -1))
        normalized.append({
            "tick": int(_get(event, "tick", 0)),
            "note": note,
            "velocity": int(_get(event, "velocity", _get(event, "vel", 0))),
            "family": _get(event, "family", ADT_DRUM_FAMILIES.get(note, f"N{note}")),
            "track": int(_get(event, "track", 0)),
            "source_index": index,
        })
    max_gap = max(2, int(round(tpq / 8)))
    high_gap = max(2, int(round(tpq / 12)))
    by_family: dict[str, list[dict]] = defaultdict(list)
    for event in normalized:
        by_family[event["family"]].append(event)

    flams = []
    grace_keys = set()
    used_indices = set()
    for family, group in by_family.items():
        if family.startswith("N"):
            continue
        seq = sorted(group, key=lambda e: (e["tick"], e["source_index"]))
        i = 0
        while i + 1 < len(seq):
            first, second = seq[i], seq[i + 1]
            gap = second["tick"] - first["tick"]
            if gap <= 0 or gap > max_gap or first["velocity"] >= second["velocity"]:
                i += 1
                continue
            third_close = i + 2 < len(seq) and 0 < seq[i + 2]["tick"] - second["tick"] <= max_gap
            ratio = first["velocity"] / max(1, second["velocity"])
            if gap <= high_gap and ratio <= 0.75 and not third_close:
                confidence = "HIGH"
            elif ratio <= 0.90 and not third_close:
                confidence = "MEDIUM"
            else:
                confidence = "LOW"
            removable = confidence in {"HIGH", "MEDIUM"} and not third_close
            item = {
                "family": family,
                "grace_tick": first["tick"], "main_tick": second["tick"],
                "gap_ticks": gap,
                "grace_note": first["note"], "main_note": second["note"],
                "grace_velocity": first["velocity"], "main_velocity": second["velocity"],
                "grace_index": first["source_index"], "main_index": second["source_index"],
                "confidence": confidence, "cluster_like": third_close,
                "remove_from_subdivision": removable,
                "grace_key": (first["tick"], first["note"], first["track"]),
            }
            flams.append(item)
            if removable:
                grace_keys.add(item["grace_key"])
            used_indices.update((first["source_index"], second["source_index"]))
            i += 2
    flams.sort(key=lambda x: (x["main_tick"], x["family"]))
    return {
        "flams": flams,
        "grace_keys": grace_keys,
        "grace_ticks": {key[0] for key in grace_keys},
        "settings": {"flam_max_gap_ticks": max_gap, "flam_high_gap_ticks": high_gap},
    }


def detect_drum_articulations(drum_events: list[dict], tpq: int, ts_segs: list) -> dict:
    """Detect flam/grace and ghost-like candidates without modifying MIDI data."""
    if not drum_events:
        return {"flams": [], "ghosts": [], "settings": {}}
    flam_analysis = detect_flams(drum_events, tpq)
    flams = []
    for item in flam_analysis["flams"]:
        bar, beat, meter = tick_to_bar_position(item["main_tick"], tpq, ts_segs)
        flams.append({**item, "bar": bar, "beat": beat, "meter": meter})

    by_family: dict[str, list[dict]] = defaultdict(list)
    for event in drum_events:
        by_family[event["family"]].append(event)
    ghosts = []
    family_stats = {}
    for family, group in by_family.items():
        if family not in GHOST_FAMILIES or len(group) < 3:
            continue
        med = float(median([e["velocity"] for e in group]))
        threshold = min(50, int(round(med * 0.60)))
        family_stats[family] = {"median_velocity": med, "threshold": threshold}
        for event in group:
            if event["velocity"] > threshold:
                continue
            key = (event["tick"], event["note"], event["track"])
            bar, beat, meter = tick_to_bar_position(event["tick"], tpq, ts_segs)
            ghosts.append({
                "bar": bar, "beat": beat, "meter": meter, "family": family,
                "tick": event["tick"], "note": event["note"], "velocity": event["velocity"],
                "threshold": threshold, "median_velocity": med,
                "flam_grace": key in flam_analysis["grace_keys"],
            })
    ghosts.sort(key=lambda x: (x["tick"], x["family"]))
    settings = dict(flam_analysis["settings"])
    settings["ghost_family_stats"] = family_stats
    return {"flams": flams, "ghosts": ghosts, "settings": settings}


def analyze_midi_rhythm(mid: MidiFile, ts_segs: list) -> dict:
    """Convenience analysis used by report-oriented clients."""
    drum_events = collect_drum_note_events(mid)
    articulations = detect_drum_articulations(drum_events, mid.ticks_per_beat, ts_segs)
    grace_ticks = {
        item["grace_tick"] for item in articulations["flams"]
        if item.get("remove_from_subdivision")
    }
    ticks = gather_note_on_ticks(mid, excluded_ticks=grace_ticks)
    return {
        "ticks": ticks,
        "subdivision": classify_subdivision(mid.ticks_per_beat, ticks),
        "bars": analyze_triplet_by_bar(ticks, mid.ticks_per_beat, ts_segs),
        "articulations": articulations,
    }
