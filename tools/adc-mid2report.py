# adc-mid2report.py (triplet-aware)
# Integrated MIDI report + triplet (swing/3-based subdivision) tendency detection.
#
# Report includes:
# - Basic file info: type, ticks_per_beat (TPQ), total length (seconds / ticks)
# - Channel usage: used channels, last effective Program/Bank, drum-channel flag
# - SysEx summary
# - Tempo / Time Signature sections (seconds-based); at the same tick, "last event wins"
# - ADT conversion hints: time signature / tempo / recommended steps_per_bar & tick_per_step
# - Subdivision analysis: straight (duplet-based) vs triplet (3-based) hit ratios, grid recommendation
#
# Usage:
#   python adc-mid2report.py INPUT.mid
#   python adc-mid2report.py -h
#
# Requirements:
#   pip install mido

import sys
import argparse
from collections import defaultdict, Counter
from statistics import median
from mido import MidiFile, MetaMessage, Message

# ---- 간단 GM Program Names (0~127) ----
GM_NAMES = [
    "Acoustic Grand", "Bright Acoustic", "Electric Grand", "Honky-tonk",
    "Electric Piano 1", "Electric Piano 2", "Harpsichord", "Clavinet",
    "Celesta", "Glockenspiel", "Music Box", "Vibraphone",
    "Marimba", "Xylophone", "Tubular Bells", "Dulcimer",
    "Drawbar Organ", "Percussive Organ", "Rock Organ", "Church Organ",
    "Reed Organ", "Accordion", "Harmonica", "Tango Accordion",
    "Acoustic Guitar (nylon)", "Acoustic Guitar (steel)",
    "Electric Guitar (jazz)", "Electric Guitar (clean)",
    "Electric Guitar (muted)", "Overdriven Guitar", "Distortion Guitar",
    "Guitar harmonics",
    "Acoustic Bass", "Electric Bass (finger)", "Electric Bass (pick)",
    "Fretless Bass", "Slap Bass 1", "Slap Bass 2", "Synth Bass 1",
    "Synth Bass 2",
    "Violin", "Viola", "Cello", "Contrabass",
    "Tremolo Strings", "Pizzicato Strings", "Orchestral Harp", "Timpani",
    "String Ensemble 1", "String Ensemble 2", "SynthStrings 1",
    "SynthStrings 2", "Choir Aahs", "Voice Oohs", "Synth Voice",
    "Orchestra Hit",
    "Trumpet", "Trombone", "Tuba", "Muted Trumpet",
    "French Horn", "Brass Section", "SynthBrass 1", "SynthBrass 2",
    "Soprano Sax", "Alto Sax", "Tenor Sax", "Baritone Sax",
    "Oboe", "English Horn", "Bassoon", "Clarinet",
    "Piccolo", "Flute", "Recorder", "Pan Flute",
    "Blown Bottle", "Shakuhachi", "Whistle", "Ocarina",
    "Lead 1 (square)", "Lead 2 (sawtooth)", "Lead 3 (calliope)",
    "Lead 4 (chiff)", "Lead 5 (charang)", "Lead 6 (voice)",
    "Lead 7 (fifths)", "Lead 8 (bass+lead)",
    "Pad 1 (new age)", "Pad 2 (warm)", "Pad 3 (polysynth)",
    "Pad 4 (choir)", "Pad 5 (bowed)", "Pad 6 (metallic)",
    "Pad 7 (halo)", "Pad 8 (sweep)",
    "FX 1 (rain)", "FX 2 (soundtrack)", "FX 3 (crystal)",
    "FX 4 (atmosphere)", "FX 5 (brightness)", "FX 6 (goblins)",
    "FX 7 (echoes)", "FX 8 (sci-fi)",
    "Sitar", "Banjo", "Shamisen", "Koto",
    "Kalimba", "Bagpipe", "Fiddle", "Shanai",
    "Tinkle Bell", "Agogo", "Steel Drums", "Woodblock",
    "Taiko Drum", "Melodic Tom", "Synth Drum", "Reverse Cymbal",
    "Guitar Fret Noise", "Breath Noise", "Seashore", "Bird Tweet",
    "Telephone Ring", "Helicopter", "Applause", "Gunshot"
]

def pp_time(sec: float) -> str:
    return f"{sec:8.3f}s"

def micros_per_qn_to_bpm(us_per_qn: int) -> float:
    return 60_000_000.0 / us_per_qn if us_per_qn else 0.0

def build_absolute_events(mid: MidiFile):
    events = []
    for ti, track in enumerate(mid.tracks):
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            events.append((abs_t, msg))
    events.sort(key=lambda x: x[0])  # stable sort
    return events

def song_end_tick(events) -> int:
    return events[-1][0] if events else 0

def last_wins_map(events, kind: str):
    d = {}
    if kind == 'tempo':
        for t, m in events:
            if isinstance(m, MetaMessage) and m.type == 'set_tempo':
                d[t] = m.tempo
    elif kind == 'timesig':
        for t, m in events:
            if isinstance(m, MetaMessage) and m.type == 'time_signature':
                d[t] = (m.numerator, m.denominator)
    else:
        raise ValueError("unknown kind")
    return sorted(d.items(), key=lambda kv: kv[0])

def build_tempo_segments(tpq: int, tempos: list, end_tick: int):
    if not tempos or tempos[0][0] != 0:
        tempos = [(0, 500000)] + tempos  # default 120 BPM
    segs = []
    cur_sec = 0.0
    for i, (t0, us0) in enumerate(tempos):
        t1 = tempos[i+1][0] if i+1 < len(tempos) else end_tick
        bpm = micros_per_qn_to_bpm(us0)
        ticks_len = max(0, t1 - t0)
        dur_sec = (us0 / 1_000_000.0) * (ticks_len / tpq)
        segs.append((t0, cur_sec, t1, cur_sec + dur_sec, us0, bpm))
        cur_sec += dur_sec
    return segs

def build_timesig_segments(timesigs: list, end_tick: int):
    if not timesigs or timesigs[0][0] != 0:
        timesigs = [(0, (4, 4))] + timesigs
    segs = []
    for i, (t0, ts) in enumerate(timesigs):
        t1 = timesigs[i+1][0] if i+1 < len(timesigs) else end_tick
        segs.append((t0, t1, ts))
    return segs

def collect_channels_and_programs(mid: MidiFile):
    ch_used = set()
    ch_prog = {ch: {'bank_msb': None, 'bank_lsb': None, 'program': None} for ch in range(16)}
    ch_drum = {ch: (ch == 9) for ch in range(16)}  # GM convention: channel 10 (index 9) is drums
    ch_note_count = defaultdict(int)

    for track in mid.tracks:
        abs_t = 0
        for msg in track:
            abs_t += msg.time
            if isinstance(msg, Message) and not msg.is_meta:
                if hasattr(msg, 'channel'):
                    ch = msg.channel
                    ch_used.add(ch)
                    if msg.type == 'control_change':
                        if msg.control == 0:   # Bank MSB
                            ch_prog[ch]['bank_msb'] = msg.value
                        elif msg.control == 32: # Bank LSB
                            ch_prog[ch]['bank_lsb'] = msg.value
                    elif msg.type == 'program_change':
                        ch_prog[ch]['program'] = msg.program
                    elif msg.type == 'note_on' and msg.velocity > 0:
                        ch_note_count[ch] += 1
    return ch_used, ch_prog, ch_drum, ch_note_count

def collect_sysex(events):
    syx = []
    for t, m in events:
        if isinstance(m, Message) and m.type == 'sysex':
            data = m.data or bytes()
            mfr = f"{data[0]:02X}" if len(data) > 0 else "--"
            syx.append((t, len(data), mfr))
    return syx

def estimate_length_seconds(tempo_segs):
    return tempo_segs[-1][3] if tempo_segs else 0.0

# ---------- Triplet detection helpers ----------

def _near(x: float, target: float, tol: float) -> bool:
    return abs(x - target) <= tol

def gather_note_on_ticks(mid: MidiFile):
    """Collect absolute tick positions of note_on events (velocity > 0). Prefer drums (GM ch10) if present."""
    events = []
    drum = []
    for track in mid.tracks:
        t = 0
        for msg in track:
            t += msg.time
            if isinstance(msg, Message) and msg.type == 'note_on' and msg.velocity > 0:
                events.append(t)
                if getattr(msg, 'channel', -1) == 9:
                    drum.append(t)
    events.sort()
    drum.sort()
    return drum if drum else events

def ioi_list(ticks):
    """Return inter-onset intervals (IOI) in ticks between consecutive note_on events."""
    out = []
    for i in range(1, len(ticks)):
        d = ticks[i] - ticks[i-1]
        if d > 0:
            out.append(d)
    return out

def triplet_vs_straight_score(tpq: int, ioi: list):
    """
    Estimate triplet vs straight (duplet-based) tendency.

    - Straight references: multiples of TPQ/4 (16th), TPQ/8 (32nd), TPQ/2 (8th), TPQ (quarter), etc.
    - Triplet references: multiples of TPQ/3 and 2*TPQ/3 (and derived multiples).
    - Tolerance: tol_ticks = max(1, TPQ//24)  (e.g., TPQ=480 -> 20 ticks)
    """
    if not ioi:
        return {'straight_hit_ratio': 0.0, 'triplet_hit_ratio': 0.0,
                'grid': 'unknown', 'details': {}}

    tol = max(1, tpq // 24)  # tolerance window
    max_ref = max(ioi + [tpq*2])

    straight_refs = []
    for unit in (tpq//8, tpq//4, tpq//2, tpq, tpq*2):
        if unit > 0:
            k = 1
            while unit*k <= max_ref:
                straight_refs.append(unit*k)
                k += 1

    triplet_refs = []
    # 기본 1/3, 2/3, 1, 4/3, 5/3, 2, ...
    base = tpq/3.0
    k = 1
    while base*k <= max_ref + tol:
        triplet_refs.append(base*k)
        k += 1

    def count_hits(values, refs):
        hits = 0
        for v in values:
            # 가장 가까운 ref가 tol 안이면 히트
            nearest = min(refs, key=lambda r: abs(r - v))
            if _near(v, nearest, tol):
                hits += 1
        return hits

    straight_hits = count_hits(ioi, straight_refs)
    triplet_hits  = count_hits(ioi, triplet_refs)

    straight_ratio = straight_hits / len(ioi)
    triplet_ratio  = triplet_hits  / len(ioi)

    # grid 결정: triplet이 확실히 크면 triplet, 아니면 straight
    # '확실히'의 기준: triplet_ratio >= straight_ratio + 0.08 또는 triplet_ratio >= 0.30
    if (triplet_ratio >= straight_ratio + 0.08) or (triplet_ratio >= 0.30):
        grid = 'triplet'
    else:
        grid = 'straight'

    return {
        'straight_hit_ratio': round(straight_ratio, 3),
        'triplet_hit_ratio':  round(triplet_ratio, 3),
        'grid': grid,
        'details': {
            'tol_ticks': tol,
            'samples': len(ioi)
        }
    }

def adt_hints(tpq, ts_segs, tempo_segs, triplet_decision=None):
    """
    ADT conversion hints:
    - Representative time signature / tempo
    - Recommended steps_per_bar:
        * 4/4 -> 16 (default)
        * 3/4 -> 12
        * 6/8 -> 12
      If triplet tendency is detected, 4/4 may be recommended as 24 (6 subdivisions per beat).
    """
    ts = ts_segs[0][2] if ts_segs else (4, 4)
    num, den = ts
    bpm = tempo_segs[0][5] if tempo_segs else 120.0

    # 기본값(스트레이트 가정)
    if (num, den) == (4, 4):
        steps_per_bar = 16
        beats_per_bar = 4
    elif (num, den) == (3, 4):
        steps_per_bar = 12
        beats_per_bar = 3
    elif (num, den) == (6, 8):
        steps_per_bar = 12
        beats_per_bar = 6
    else:
        steps_per_bar = max(8, 4 * num)
        beats_per_bar = num

    # Triplet tendency detection 시 보정
    if triplet_decision and triplet_decision.get('grid') == 'triplet':
        if (num, den) == (4, 4):
            steps_per_bar = 24   # 4/4에서 트리플렛 많으면 박당 6 subdiv (총 24)
        # 3/4, 6/8은 기본 12가 이미 트리플렛 친화적

    tick_per_step = (tpq * beats_per_bar) / steps_per_bar
    return {
        'time_signature': f"{num}/{den}",
        'bpm': round(bpm, 3),
        'steps_per_bar': int(steps_per_bar),
        'tick_per_step': tick_per_step
    }

# ---------- Main report ----------

def main(path: str):
    mid = MidiFile(path)
    events = build_absolute_events(mid)
    end_t = song_end_tick(events)
    tpq = mid.ticks_per_beat
    typ = mid.type

    # Meta: tempo / time signature (at the same tick, last event wins)
    tempos  = last_wins_map(events, 'tempo')
    timesig = last_wins_map(events, 'timesig')
    tempo_segs = build_tempo_segments(tpq, tempos, end_t)
    ts_segs    = build_timesig_segments(timesig, end_t)

    eff_us0 = tempo_segs[0][4] if tempo_segs else 500000
    eff_bpm = micros_per_qn_to_bpm(eff_us0)
    eff_ts  = ts_segs[0][2] if ts_segs else (4, 4)

    # Channels / programs
    ch_used, ch_prog, ch_drum, ch_note_count = collect_channels_and_programs(mid)

    # SysEx
    sysex_list = collect_sysex(events)

    # Total length (seconds)
    total_sec = estimate_length_seconds(tempo_segs)

    # Triplet tendency detection
    ticks = gather_note_on_ticks(mid)
    ioi = ioi_list(ticks)
    subdiv = triplet_vs_straight_score(tpq, ioi)

    # ADT hints (triplet-aware)
    hints = adt_hints(tpq, ts_segs, tempo_segs, subdiv)

    # --------- Output ---------
    print("============================================================")
    print(f"File: {path}")
    print(f"Type: {typ}   TPQ: {tpq}   EndTick: {end_t}   Length: {total_sec:.3f}s")
    print(f"Effective @0  Tempo: {eff_bpm:.3f} BPM   TimeSig: {eff_ts[0]}/{eff_ts[1]}")
    print("============================================================\n")

    print(f"Channels Used: {len(ch_used)}  -> {sorted(ch_used)}")
    active_note_ch = sorted([ch for ch, n in ch_note_count.items() if n > 0])
    setup_only_ch  = sorted([ch for ch in ch_used if ch_note_count.get(ch,0) == 0])
    print(f"  Active note channels: {active_note_ch}  (played notes)")
    print(f"  Setup-only channels : {setup_only_ch}   (CC/PC etc., no notes)")
    print()
    print("Per-Channel Program/Bank (last effective):")
    print("  ch  drum  bank(msb:lsb)  program  name                          notes")
    for ch in range(16):
        if ch in ch_used or ch == 9:
            msb = ch_prog[ch]['bank_msb']
            lsb = ch_prog[ch]['bank_lsb']
            pgm = ch_prog[ch]['program']
            name = GM_NAMES[pgm] if (pgm is not None and 0 <= pgm <= 127) else "-"
            notes = ch_note_count.get(ch, 0)
            print(f"  {ch:2d}  {str(ch_drum[ch]):<5}  "
                  f"{'-' if msb is None else msb:>3}:{'-' if lsb is None else lsb:<3}   "
                  f"{'-' if pgm is None else pgm:>3}     {name:<28}  {notes:6d}")
    print()

    if sysex_list:
        print("SysEx Messages:")
        print("  tick       length  mfr_id(hex)")
        for t, ln, mfr in sysex_list:
            print(f"  {t:10d}   {ln:6d}   {mfr}")
    else:
        print("SysEx Messages: (none)")
    print()

    print("Tempo Map (sections):")
    print("  start_tick @ start_sec  ->  BPM   |  end_tick @ end_sec   (dur)")
    for (t0, s0, t1, s1, us, bpm) in tempo_segs:
        print(f"{t0:12d} @ {pp_time(s0)} -> {bpm:7.3f} | "
              f"{t1:12d} @ {pp_time(s1)}  (Δ {pp_time(s1 - s0)})")
    print()

    print("Time Signatures (sections):")
    print("  start_tick -> end_tick : numer/denom")
    for (t0, t1, (n, d)) in ts_segs:
        print(f"{t0:10d} -> {t1:10d} : {n}/{d}")
    print()

    print("ADT Conversion Hints:")
    print(f"  time_signature : {hints['time_signature']}")
    print(f"  bpm            : {hints['bpm']}")
    print(f"  steps_per_bar  : {hints['steps_per_bar']}")
    print(f"  tick_per_step  : {hints['tick_per_step']:.3f}")
    print()

    print("Subdivision Analysis:")
    print(f"  grid                  : {subdiv['grid']}  "
          f"(triplet_hit={subdiv['triplet_hit_ratio']}, straight_hit={subdiv['straight_hit_ratio']})")
    det = subdiv['details']
    print(f"  samples={det.get('samples',0)}, tol_ticks={det.get('tol_ticks','-')}")
    if subdiv['grid'] == 'straight' and hints['steps_per_bar'] in (12, 24):
        print("  note: Time signature is triplet-friendly, but IOI indicates a straight feel → using default recommendation.")
    elif subdiv['grid'] == 'triplet' and hints['steps_per_bar'] == 16:
        print("  note: Triplet tendency detected → 24 steps recommended (in 4/4 context).")


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="adc-mid2report.py",
        description=(
            "MIDI inspection tool that prints an integrated report including tempo/time-signature sections, "
            "channel usage, SysEx summary, ADT conversion hints, and straight vs triplet subdivision tendency."
        ),
    )
    p.add_argument("midi_file", help="Input MIDI file (.mid)")
    return p


if __name__ == "__main__":
    import argparse

    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        main(args.midi_file)
    except FileNotFoundError:
        print(f"error: file not found: {args.midi_file}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
