#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adc-patternlab.py 260729k

One MIDI -> self-contained interactive HTML/SVG whole-file drum matrix.
Click the SVG to toggle RAW GM notes and two-bar SLOT_MAP display.
Slot maps are loaded from canonical JSON; rhythm analysis uses adc_rhythm_analysis.
"""
from __future__ import annotations
import argparse, html, json, math, sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple
from mido import Message, MetaMessage, MidiFile

from adc_rhythm_analysis import classify_subdivision, detect_flams

SCRIPT_NAME="adc-patternlab.py"; VERSION="260729k"; VERSION_TEXT=f"{SCRIPT_NAME} {VERSION}"
GHOST_CANDIDATE_MAX_VELOCITY=30
GM={35:"Acoustic Bass Drum",36:"Bass Drum 1",37:"Side Stick",38:"Acoustic Snare",39:"Hand Clap",40:"Electric Snare",41:"Low Floor Tom",42:"Closed Hi-Hat",43:"High Floor Tom",44:"Pedal Hi-Hat",45:"Low Tom",46:"Open Hi-Hat",47:"Low-Mid Tom",48:"Hi-Mid Tom",49:"Crash Cymbal 1",50:"High Tom",51:"Ride Cymbal 1",52:"Chinese Cymbal",53:"Ride Bell",54:"Tambourine",55:"Splash Cymbal",56:"Cowbell",57:"Crash Cymbal 2",58:"Vibraslap",59:"Ride Cymbal 2",60:"Hi Bongo",61:"Low Bongo",62:"Mute Hi Conga",63:"Open Hi Conga",64:"Low Conga",65:"High Timbale",66:"Low Timbale",67:"High Agogo",68:"Low Agogo",69:"Cabasa",70:"Maracas",71:"Short Whistle",72:"Long Whistle",73:"Short Guiro",74:"Long Guiro",75:"Claves",76:"Hi Wood Block",77:"Low Wood Block",78:"Mute Cuica",79:"Open Cuica",80:"Mute Triangle",81:"Open Triangle"}

@dataclass(frozen=True)
class Slot: label:str; notes:Tuple[int,...]
@dataclass(frozen=True)
class SMap:
    id:int; name:str; slots:Tuple[Slot,...]
    @property
    def accepted(self)->Set[int]:
        s=set()
        for x in self.slots:s.update(x.notes)
        return s

def load_slot_maps(path: Path) -> Tuple[SMap, ...]:
    """Load and validate the sole authoritative slot-map JSON definition."""
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"slot-map definition not found: {path}") from exc
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError(f"cannot load slot-map definition {path}: {exc}") from exc
    if not isinstance(data,list) or not data:
        raise ValueError("slot-map JSON root must be a non-empty array")
    maps=[]; seen_ids=set(); seen_names=set()
    for row in data:
        if not isinstance(row,dict):raise ValueError("each slot map must be an object")
        mid=row.get("slot_map_id"); name=row.get("name"); slots_data=row.get("slots")
        if not isinstance(mid,int) or mid in seen_ids:raise ValueError(f"invalid or duplicate slot_map_id: {mid!r}")
        if not isinstance(name,str) or not name or name in seen_names:raise ValueError(f"invalid or duplicate slot-map name: {name!r}")
        if not isinstance(slots_data,list) or not 1<=len(slots_data)<=12:raise ValueError(f"{name}: slots must contain 1..12 entries")
        seen_ids.add(mid); seen_names.add(name); slots=[]; seen_slots=set()
        for item in slots_data:
            slot_no=item.get("slot"); label=item.get("abbrev"); allowed=item.get("midi_input_allowed"); rep=item.get("representative_midi")
            if not isinstance(slot_no,int) or slot_no in seen_slots:raise ValueError(f"{name}: invalid or duplicate slot number {slot_no!r}")
            if not isinstance(label,str) or not label:raise ValueError(f"{name} slot {slot_no}: missing abbrev")
            if not isinstance(allowed,list) or not allowed or any(not isinstance(n,int) for n in allowed):raise ValueError(f"{name} slot {slot_no}: invalid midi_input_allowed")
            if rep not in allowed:raise ValueError(f"{name} slot {slot_no}: representative_midi must be allowed")
            seen_slots.add(slot_no); slots.append((slot_no,Slot(label,tuple(allowed))))
        expected=list(range(len(slots)))
        actual=sorted(seen_slots)
        if actual!=expected:raise ValueError(f"{name}: slot numbers must be contiguous 0..{len(slots)-1}")
        maps.append(SMap(mid,name,tuple(slot for _,slot in sorted(slots))))
    maps.sort(key=lambda m:m.id)
    return tuple(maps)

MAPS:Tuple[SMap,...]=()


@dataclass
class Ev: tick:int; note:int; vel:int; dur:int=0
@dataclass
class Bar: no:int; start:int; end:int; num:int; den:int
@dataclass
class Block: no:int; bars:List[Bar]; start:int; end:int; events:List[Ev]; smap:SMap; unknown:List[int]; subdiv:dict; pattern_no:int=0; duplicate_of:Optional[int]=None; ending_hit:bool=False



def embedded_header_metadata(mid):
    """Return only tempo/time-signature metadata explicitly stored in the SMF.

    No 120 BPM or 4/4 fallback is reported here. Events duplicated across
    tracks at the same tick are collapsed for header-display purposes.
    """
    tempos=[]
    timesigs=[]
    for tr in mid.tracks:
        tick=0
        for m in tr:
            tick+=m.time
            if isinstance(m,MetaMessage) and m.type=="set_tempo":
                tempos.append((tick,int(m.tempo)))
            elif isinstance(m,MetaMessage) and m.type=="time_signature":
                timesigs.append((tick,int(m.numerator),int(m.denominator)))
    tempos=sorted(set(tempos))
    timesigs=sorted(set(timesigs))
    parts=[]
    if len(tempos)==1:
        bpm=60000000/tempos[0][1]
        bpm_text=str(int(round(bpm))) if abs(bpm-round(bpm))<0.005 else f"{bpm:.2f}".rstrip("0").rstrip(".")
        parts.append(f"{bpm_text} BPM")
    elif len(tempos)>1:
        parts.append(f"tempo changes ×{len(tempos)}")
    if len(timesigs)==1:
        _,num,den=timesigs[0]
        parts.append(f"{num}/{den}")
    elif len(timesigs)>1:
        parts.append(f"time-signature changes ×{len(timesigs)}")
    return parts

def collect(mid):
    ev=[]; ts=[]; mx=0
    for tr in mid.tracks:
        t=0; active={}
        for m in tr:
            t+=m.time; mx=max(mx,t)
            if isinstance(m,MetaMessage) and m.type=="time_signature":
                ts.append((t,int(m.numerator),int(m.denominator)))
            elif isinstance(m,Message) and getattr(m,"channel",-1)==9:
                if m.type=="note_on" and m.velocity>0:
                    key=int(m.note); active.setdefault(key,[]).append((t,int(m.velocity)))
                elif m.type=="note_off" or (m.type=="note_on" and m.velocity==0):
                    key=int(m.note)
                    if active.get(key):
                        st,vel=active[key].pop(0); ev.append(Ev(st,key,vel,max(0,t-st)))
        for key,items in active.items():
            for st,vel in items:
                ev.append(Ev(st,key,vel,0))
    d={0:(4,4)}
    for t,n,q in ts:d[t]=(n,q)
    return sorted(ev,key=lambda x:(x.tick,x.note,x.vel,x.dur)),[(t,*v) for t,v in sorted(d.items())],max(mx,(ev[-1].tick+1 if ev else 1))

def make_bars(tpq,ts,mx):
    out=[]; t=0; i=0; no=1
    while t<mx:
        while i+1<len(ts) and ts[i+1][0]<=t:i+=1
        _,n,d=ts[i]; end=t+max(1,round(tpq*n*4/d))
        if i+1<len(ts) and t<ts[i+1][0]<end:end=ts[i+1][0]
        out.append(Bar(no,t,end,n,d)); t=end; no+=1
    return out

def choose(notes):
    """Choose the lowest-ID exact SLOT_MAP, or the nearest map with warning.

    If no map is a complete cover, every map participates in the comparison.
    The map covering the most distinct notes wins; ties prefer fewer unused
    accepted notes and finally the stable lower ID, so LEGACY (ID 0) remains
    the conservative default.
    """
    if not notes:
        return MAPS[0], []

    exact=[m for m in MAPS if notes <= m.accepted]
    if exact:
        m=min(exact,key=lambda z:z.id)
        return m, []

    def score(m):
        covered=len(notes & m.accepted)
        missing=len(notes - m.accepted)
        unused=len(m.accepted - notes)
        return (covered,-missing,-m.id,-unused)

    m=max(MAPS,key=score)
    return m,sorted(notes-m.accepted)

def _is_ending_hit_block(block_bars, events):
    if len(block_bars)!=1 or not events:
        return False
    first_tick=min(e.tick for e in events)
    onset_group=[e for e in events if e.tick==first_tick]
    tol=max(1,(block_bars[0].end-block_bars[0].start)//96)
    near_start=(first_tick-block_bars[0].start)<=tol
    return near_start and len(onset_group)==len(events)

def _pattern_signature(block):
    return tuple(sorted((e.tick-block.start,e.note,e.vel,e.dur) for e in block.events))

def blocks(bars,ev,tpq):
    out=[]
    for i in range(0,len(bars),2):
        bb=bars[i:i+2]; s,e=bb[0].start,bb[-1].end; ee=[x for x in ev if s<=x.tick<e]; m,u=choose({x.note for x in ee})
        flam_analysis=detect_flams(ee,tpq)
        grace_indices={item["grace_index"] for item in flam_analysis["flams"] if item.get("remove_from_subdivision")}
        sub=classify_subdivision(tpq,[x.tick for idx,x in enumerate(ee) if idx not in grace_indices]); sub["tpq"]=tpq
        out.append(Block(len(out)+1,bb,s,e,ee,m,u,sub))
    if out and _is_ending_hit_block(out[-1].bars,out[-1].events):
        out[-1].ending_hit=True
    seen={}; next_pattern=1
    for b in out:
        if b.ending_hit:
            continue
        sig=_pattern_signature(b)
        if sig in seen:
            first=seen[sig]; b.pattern_no=first.pattern_no; b.duplicate_of=first.no
        else:
            b.pattern_no=next_pattern; seen[sig]=b; next_pattern+=1
    return out

def tx(x,y,s,cls="",anchor="start"):return f'<text x="{x:.1f}" y="{y:.1f}" class="{cls}" text-anchor="{anchor}">{html.escape(s)}</text>'
def slot_index(m,n):
    for i,s in enumerate(m.slots):
        if n in s.notes:return i
    return None

def accent_level(velocity):
    """Map MIDI velocity to the ADT-style four-level accent display."""
    if velocity <= 31:return 0,"pp"
    if velocity <= 63:return 1,"p"
    if velocity <= 95:return 2,"mf"
    return 3,"ff"

def reference_card(b,x,y,w=430,h=260):
    bars=str(b.bars[0].no) if len(b.bars)==1 else f'{b.bars[0].no}–{b.bars[-1].no}'
    p=[f'<g class="block duplicate {"bad" if b.unknown else ""}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>']
    p += [tx(x+16,y+28,f'B{b.no:03d}  bars {bars}',"title"),tx(x+w/2,y+105,f'Pattern #{b.pattern_no:03d}',"dup-pattern","middle"),tx(x+w/2,y+139,f'Same as B{b.duplicate_of:03d}',"dup-same","middle"),tx(x+w/2,y+169,f'ID {b.smap.id} {b.smap.name} · matrix omitted',"meta","middle"),tx(x+w/2,y+192,('MISSING NOTES: '+','.join(map(str,b.unknown))) if b.unknown else '',"warning","middle"),tx(x+16,y+h-16,'duplicate checked within this MIDI file only',"meta"),'</g>']
    return ''.join(p)

def ending_card(b,x,y,w=430,h=260):
    notes=', '.join(f'{e.note}({e.vel})' for e in b.events) or '(none)'
    bar=str(b.bars[0].no)
    p=[f'<g class="block ending"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>']
    p += [tx(x+16,y+28,f'B{b.no:03d}  bar {bar}',"title"),tx(x+w/2,y+100,'ENDING HIT',"ending-title","middle"),tx(x+w/2,y+134,'excluded from pattern catalog',"dup-same","middle"),tx(x+w/2,y+166,f'notes: {notes}',"meta","middle"),tx(x+16,y+h-16,'single onset group at the start of the final odd bar',"meta"),'</g>']
    return ''.join(p)

def card(b,x,y,w=430,h=260):
    beats=max(1.0,(b.end-b.start)/max(1,b.subdiv.get("tpq",1)))
    subdivision=b.subdiv.get("subdivision","unknown")
    cells_per_beat=6 if subdivision=="triplet-16T" else 3 if subdivision=="triplet-8T" else 4
    cols=max(1,round(beats*cells_per_beat))
    major_every=cells_per_beat
    hh,fh,lw=58,28,96; gx,gy=x+lw,y+hh; gw,gh=w-lw-8,h-hh-fh
    raw=sorted({e.note for e in b.events},reverse=True) or [36]; slots=list(range(len(b.smap.slots)-1,-1,-1)); p=[]
    p.append(f'<g class="block {"bad" if b.unknown else ""}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" class="bg"/>')
    bars=str(b.bars[0].no) if len(b.bars)==1 else f'{b.bars[0].no}–{b.bars[-1].no}'; meters=[f'{z.num}/{z.den}' for z in b.bars]; meter=meters[0] if len(set(meters))==1 else '→'.join(meters)
    p += [tx(x+10,y+18,f'B{b.no:03d}  bars {bars} · Pattern #{b.pattern_no:03d}',"title"),tx(x+10,y+36,f'{meter} · {len(b.events)} hits · {cells_per_beat} cells/beat',"meta"),tx(x+w-10,y+18,f'ID {b.smap.id} {b.smap.name}',"sid","end"),tx(x+w-10,y+36,f'{b.subdiv["subdivision"]} · {b.subdiv["confidence"]}',"meta","end")]
    if b.unknown:p.append(tx(x+w/2,y+52,'MISSING NOTES: '+','.join(map(str,b.unknown)),"warning","middle"))
    # Draw subdivision lines, beat lines, and bar boundaries separately so
    # a straight-16 grid is visually unmistakable: four cells per beat.
    for c in range(cols+1):
        xx=gx+c*gw/cols
        cl="guide major" if c%major_every==0 else "guide"
        p.append(f'<line x1="{xx:.2f}" y1="{gy}" x2="{xx:.2f}" y2="{gy+gh}" class="{cl}"/>')
    for bar in b.bars:
        frac=(bar.start-b.start)/max(1,b.end-b.start)
        xx=gx+frac*gw
        p.append(f'<line x1="{xx:.2f}" y1="{gy-4}" x2="{xx:.2f}" y2="{gy+gh}" class="barline"/>')
    p.append(f'<line x1="{gx+gw:.2f}" y1="{gy-4}" x2="{gx+gw:.2f}" y2="{gy+gh}" class="barline"/>')
    p.append('<g class="raw">'); rh=gh/len(raw); rmap={n:i for i,n in enumerate(raw)}
    for i,n in enumerate(raw):
        yy=gy+i*rh; p += [tx(x+8,yy+rh*.7,f'{n} {GM.get(n,"non-GM")}',"row"),f'<line x1="{gx}" y1="{yy+rh:.2f}" x2="{gx+gw}" y2="{yy+rh:.2f}" class="rguide"/>']
    # RAW notes are placed at the centers of subdivision cells rather than on
    # grid lines.  This keeps the matrix readable as a step-pattern display.
    # Same-note close pairs within one 16T interval are conservative flam
    # candidates.  Both share the main note's cell center on the time axis; the
    # hollow grace circle is displaced upward inside the same raw-note row.
    flam_analysis=detect_flams(b.events,b.subdiv.get("tpq",1))
    pairs=[]; pair_role={}; pair_delta={}; pair_confidence={}
    for item in flam_analysis["flams"]:
        grace=b.events[item["grace_index"]]; main=b.events[item["main_index"]]; delta=item["gap_ticks"]
        pairs.append((grace,main,delta))
        pair_role[id(grace)]="grace"; pair_role[id(main)]="main"
        pair_delta[id(grace)]=pair_delta[id(main)]=delta
        pair_confidence[id(grace)]=pair_confidence[id(main)]=item["confidence"]
    flam_threshold=flam_analysis["settings"].get("flam_max_gap_ticks",0)
    cell_w=gw/cols
    def raw_cell_center(event):
        c=max(0,min(cols-1,math.floor((event.tick-b.start)/max(1,b.end-b.start)*cols+0.5)))
        return gx+(c+.5)*cell_w
    xpos={id(e):raw_cell_center(e) for e in b.events}
    for grace,main,delta in pairs:
        # A flam is one slot-level event for display purposes.  Anchor both
        # circles to the main hit's quantized cell and use Y only to reveal grace.
        xpos[id(grace)]=xpos[id(main)]
    grace_offset=min(10.0,max(5.0,rh*.22))
    for e in b.events:
        cx=xpos[id(e)]; base_cy=gy+(rmap[e.note]+.5)*rh; rr=2+2.2*e.vel/127
        role=pair_role.get(id(e))
        cy=base_cy-grace_offset if role=="grace" else base_cy
        classes=["hit","rawhit"]
        if e.note in b.unknown:classes.append("unknown")
        if e.vel<=GHOST_CANDIDATE_MAX_VELOCITY:classes.append("ghost")
        if role=="grace":classes.append("flamgrace")
        if role=="main":classes.append("flammain")
        labels=[]
        if e.vel<=GHOST_CANDIDATE_MAX_VELOCITY:labels.append("ghost candidate")
        if role:labels.append(f"flam candidate ({role}, {pair_confidence[id(e)]}, delta {pair_delta[id(e)]} ticks, threshold {flam_threshold})")
        extra=("; "+"; ".join(labels)) if labels else ""
        p.append(f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{rr:.2f}" class="{" ".join(classes)}"><title>note {e.note}, velocity {e.vel}, duration {e.dur}, tick {e.tick}{extra}</title></circle>')
    p.append('</g><g class="slot">'); sh=gh/len(slots); smap={s:i for i,s in enumerate(slots)}
    for i,si in enumerate(slots):
        yy=gy+i*sh; s=b.smap.slots[si]; p += [tx(x+8,yy+sh*.7,f'{si:02d} {s.label} [{",".join(map(str,s.notes))}]',"row"),f'<line x1="{gx}" y1="{yy+sh:.2f}" x2="{gx+gw}" y2="{yy+sh:.2f}" class="rguide"/>']
    # SLOT view uses one full cell per quantized step. If several raw notes
    # collapse into the same slot/cell, retain the strongest velocity.
    cells={}
    for e in b.events:
        si=slot_index(b.smap,e.note)
        if si is None:continue
        c=max(0,min(cols-1,math.floor((e.tick-b.start)/max(1,b.end-b.start)*cols+0.5)))
        key=(si,c)
        prev=cells.get(key)
        if prev is None or e.vel>prev.vel:cells[key]=e
    cell_w=gw/cols
    for (si,c),e in sorted(cells.items(),key=lambda item:(smap[item[0][0]],item[0][1])):
        row=smap[si]; xx=gx+c*cell_w; yy=gy+row*sh; level,accent=accent_level(e.vel)
        p.append(f'<rect x="{xx+.6:.2f}" y="{yy+.6:.2f}" width="{max(.5,cell_w-1.2):.2f}" height="{max(.5,sh-1.2):.2f}" rx="1.2" class="slotcell accent{level}"><title>slot {si} {b.smap.slots[si].label}; raw {e.note}; velocity {e.vel}; duration {e.dur}; accent {level} ({accent})</title></rect>')
    p.append('</g>'); foot='click SVG: RAW ↔ SLOT' if not b.unknown else 'WARNING · nearest SLOT_MAP used · missing notes: '+','.join(map(str,b.unknown)); p += [tx(x+10,y+h-9,foot,"meta"),'</g>']; return ''.join(p)

def render(path,mid,bars_,bb):
    cw,ch,gx,gy,mar,ncol=430,260,18,18,18,3; nrow=max(1,math.ceil(len(bb)/ncol)); sw=mar*2+ncol*cw+(ncol-1)*gx; sh=mar*2+nrow*ch+(nrow-1)*gy
    body=[]
    for i,b in enumerate(bb):
        x=mar+(i%ncol)*(cw+gx); y=mar+(i//ncol)*(ch+gy)
        body.append(ending_card(b,x,y) if b.ending_hit else reference_card(b,x,y) if b.duplicate_of is not None else card(b,x,y))
    notes=sorted({e.note for b in bb for e in b.events}); summary={}
    for b in bb:
        if not b.ending_hit and b.duplicate_of is None:summary[f'{b.smap.id} {b.smap.name}']=summary.get(f'{b.smap.id} {b.smap.name}',0)+1
    unique_count=sum(1 for b in bb if not b.ending_hit and b.duplicate_of is None); duplicate_count=sum(1 for b in bb if b.duplicate_of is not None); ending_count=sum(1 for b in bb if b.ending_hit)
    header_parts=[f"SMF Type {mid.type}",f"TPQ {mid.ticks_per_beat}"]
    header_parts.extend(embedded_header_metadata(mid))
    header_parts.extend([f"{len(bars_)} bar(s)",f"{len(bb)} two-bar block(s)",f"unique patterns {unique_count}",f"duplicates {duplicate_count}",f"ending hits {ending_count}",f"CH10 notes: {', '.join(map(str,notes)) or '(none)'}"])
    header_summary=html.escape(" · ".join(header_parts))
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(path.name)} — ADC PatternLab</title><style>
:root{{--bg:#f4f6f8;--panel:#fff;--ink:#17202a;--muted:#65717e;--line:#d9dee4;--major:#9aa6b2;--raw:#1f6feb;--slot:#8a3ffc;--warn:#c2410c;--a0:#dbeafe;--a1:#93c5fd;--a2:#3b82f6;--a3:#1e3a8a}}@media(prefers-color-scheme:dark){{:root{{--bg:#11151a;--panel:#1a2027;--ink:#e6edf3;--muted:#9da9b5;--line:#303843;--major:#66717d;--raw:#58a6ff;--slot:#c297ff;--warn:#ff9b6a;--a0:#23395d;--a1:#2f6fab;--a2:#58a6ff;--a3:#b6d8ff}}}}*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,sans-serif;background:var(--bg);color:var(--ink)}}header{{position:sticky;top:0;z-index:3;padding:14px 18px 12px;background:var(--panel);border-bottom:1px solid var(--line)}}h1{{margin:0 0 6px;font-size:20px}}.summary{{font-size:13px;color:var(--muted)}}button{{margin-top:8px;padding:7px 11px;border:1px solid var(--line);border-radius:7px;background:var(--panel);color:var(--ink);font-weight:700;cursor:pointer}}.legend{{margin-left:14px;font-size:12px;color:var(--muted)}}.lg{{display:inline-block;width:12px;height:12px;margin:0 3px 0 7px;vertical-align:-2px;border:1px solid var(--line)}}.a0{{background:var(--a0)}}.a1{{background:var(--a1)}}.a2{{background:var(--a2)}}.a3{{background:var(--a3)}}main{{overflow:auto;padding:12px}}svg{{display:block;cursor:pointer;user-select:none}}.bg{{fill:var(--panel);stroke:var(--line)}}.bad .bg{{stroke:var(--warn);stroke-width:2}}.title{{fill:var(--ink);font-size:13px;font-weight:750}}.meta{{fill:var(--muted);font-size:10px}}.sid{{fill:var(--slot);font-size:12px;font-weight:800}}.warning{{fill:var(--warn);font-size:10px;font-weight:800}}.row{{fill:var(--ink);font-size:8.5px}}.guide,.rguide{{stroke:var(--line);stroke-width:.7}}.major{{stroke:var(--major);stroke-width:1.45}}.barline{{stroke:var(--ink);stroke-width:2.1;opacity:.72}}.hit{{opacity:1}}.rawhit{{fill:var(--raw);stroke:var(--panel);stroke-width:.8}}.ghost{{stroke:var(--ink);stroke-width:1;stroke-dasharray:2 1}}.flamgrace{{fill:var(--panel);stroke:var(--raw);stroke-width:1.5;stroke-dasharray:none;opacity:1}}.flammain{{stroke:var(--raw);stroke-width:.6}}.slothit{{fill:var(--slot)}}.slotcell{{stroke:var(--panel);stroke-width:.35}}.accent0{{fill:var(--a0)}}.accent1{{fill:var(--a1)}}.accent2{{fill:var(--a2)}}.accent3{{fill:var(--a3)}}.unknown{{fill:var(--warn);stroke:var(--panel)}}.slot{{display:none}}svg.slotmode .raw{{display:none}}svg.slotmode .slot{{display:inline}}details{{margin:0 18px 18px;padding:10px;border:1px solid var(--line);border-radius:8px;background:var(--panel)}}
</style></head><body><header><h1>{html.escape(path.name)} — ADC PatternLab</h1><div class="summary">{header_summary}</div><button id="toggle">Toggle RAW / SLOT</button> <strong id="mode">RAW GM NOTES</strong><span class="legend"> Accent: <i class="lg a0"></i>0 (1–31) <i class="lg a1"></i>1 (32–63) <i class="lg a2"></i>2 (64–95) <i class="lg a3"></i>3 (96–127)</span><span class="legend">RAW: ○ flam grace · dashed ring ghost candidate (velocity ≤ 30)</span></header><main><svg id="matrix" xmlns="http://www.w3.org/2000/svg" width="{sw}" height="{sh}" viewBox="0 0 {sw} {sh}">{''.join(body)}</svg></main><details><summary>Analysis notes</summary><p>Each block is checked only against earlier blocks in the same MIDI file. Exact identity uses relative tick, raw note, velocity, and note duration. A repeated block keeps its original Pattern number and omits the matrix drawing.</p><p>A final odd bar containing only one onset group at its beginning is labeled ENDING HIT and excluded from the pattern catalog.</p><p>The horizontal grid follows the detected subdivision: straight-16 uses 4 cells per beat, 8T uses 3, and 16T uses 6. Mixed or unknown material defaults to the straight 4-cell grid.</p><p>If no SLOT_MAP covers every note, the nearest map is used, the card receives a red border, and uncovered MIDI notes are listed as MISSING NOTES. Ties fall back conservatively toward lower IDs, beginning with LEGACY 12.</p><p>RAW view places every hit at the center of its detected subdivision cell rather than on a grid line. Velocity controls circle size. Velocity ≤ 30 is marked as a ghost candidate with a dashed ring. Two consecutive hits in the same ADT drum family are marked as flam candidates only when the earlier hit is softer and the gap is no more than TPQ/8; confidence and the true tick delta are retained in tooltips. The main hit remains at the row center; the earlier grace hit is a hollow circle placed slightly above it in the same row and at the same cell-center X position. Tooltips retain the true tick delta.</p><p>In SLOT view, each hit fills its complete quantized cell. Cell color shows four velocity/accent levels: 0=1–31, 1=32–63, 2=64–95, 3=96–127. Ghost/flam candidates are intentionally not shown there. When multiple raw hits collapse into one slot/cell, the strongest velocity is shown.</p><p>SLOT_MAP usage: <code>{html.escape(json.dumps(summary,ensure_ascii=False))}</code></p><p>Shared adc_rhythm_analysis per-block subdivision: straight-only 1/4,3/4; 8T 1/3,2/3; 16T-only 1/6,5/6; beat anchors and shared 1/2 excluded. A 16T label additionally requires dominant evidence at both exclusive 16T phases, preventing isolated off-grid hits from being overclassified.</p></details><script>(()=>{{const s=document.getElementById('matrix'),m=document.getElementById('mode');function t(){{const v=s.classList.toggle('slotmode');m.textContent=v?'2-BAR SLOT_MAP':'RAW GM NOTES'}}s.addEventListener('click',t);document.getElementById('toggle').addEventListener('click',t)}})();</script></body></html>'''

def main(argv=None):
    p=argparse.ArgumentParser(prog=SCRIPT_NAME,description="Generate an interactive HTML/SVG drum pattern catalog from one MIDI file."); p.add_argument("input_midi",type=Path); p.add_argument("-o","--output",type=Path); p.add_argument("--slot-maps",type=Path,help="Canonical slot_map_definitions.json (default: beside this script)"); p.add_argument("--version",action="version",version=VERSION_TEXT); a=p.parse_args(argv)
    if not a.input_midi.is_file():print(f'[ERROR] not found: {a.input_midi}',file=sys.stderr);return 2
    slot_map_path=a.slot_maps or Path(__file__).with_name("slot_map_definitions.json")
    global MAPS
    try:MAPS=load_slot_maps(slot_map_path)
    except ValueError as e:print(f'[ERROR] {e}',file=sys.stderr);return 2
    try:mid=MidiFile(str(a.input_midi))
    except Exception as e:print(f'[ERROR] cannot read MIDI: {e}',file=sys.stderr);return 2
    ev,ts,mx=collect(mid); bars_=make_bars(mid.ticks_per_beat,ts,mx); bb=blocks(bars_,ev,mid.ticks_per_beat); out=a.output or a.input_midi.with_name(a.input_midi.stem+'_patternlab.html'); out.write_text(render(a.input_midi,mid,bars_,bb),encoding='utf-8'); print(VERSION_TEXT); print(f'[OK] {out}'); print(f'[OK] bars={len(bars_)}, blocks={len(bb)}, drum_note_on={len(ev)}'); return 0
if __name__=='__main__':raise SystemExit(main())
