# 6MISC2.MID Split Notice

## Background

The original **6MISC2.MID** contained two different musical meters within a single MIDI file.

- **Bars 1–24:** Miscellaneous **4/4** drum patterns
- **Bars 25–34:** Five **2-bar 3/4 waltz** drum patterns

Although this organization is acceptable for manual browsing, it complicates automated processing because analysis and conversion tools generally assume that all patterns in a MIDI file share the same time signature.

Examples include:

- rhythm classification
- meter detection
- bar counting
- ADT/ADP conversion
- pattern indexing

To simplify automated processing, the file has been divided into two independent MIDI files.

---

# Split Point

The split was performed at the beginning of the first waltz pattern.

```
Original 6MISC2.MID

Bars
 1                                                     24 | 25                    34
┌────────────────────────────────────────────────────────┼──────────────────────────┐
│                  4/4 Miscellaneous Patterns            │  Five 2-bar Waltz Patterns│
└────────────────────────────────────────────────────────┼──────────────────────────┘
                                                         ▲
                                                         │
                                            Split Point (25:01:000)
```

The split point corresponds to:

- **Bar 25**
- **Beat 1**
- **Time position 25:01:000** (Anvil Studio)

which is the first measure of the waltz section.

---

# Resulting Files

| File | Contents |
|------|----------|
| **6MISC3.MID** | 24 bars of miscellaneous 4/4 drum patterns |
| **6WALTZ.MID** | Five 2-bar (10-bar total) 3/4 waltz drum patterns |

---

# Time Signature Update

The original file did not distinguish the waltz section with its own MIDI Time Signature event.

To improve compatibility with MIDI editors and automatic analysis tools, the new file

**6WALTZ.MID**

has been updated to include the following MIDI Meta Event at the beginning of the track:

```
Time Signature: 3/4
```

No musical data has been altered.

Only the Time Signature metadata was added.

---

# Why Split the File?

Separating the two meters provides several advantages.

- One consistent meter per MIDI file
- Simpler rhythm analysis
- Reliable ADT/ADP conversion
- Correct bar numbering in MIDI editors
- Easier pattern indexing
- Better compatibility with DAWs and MIDI sequencers

This also allows automated tools to recognize the rhythmic style without requiring manual intervention.

---

# Musical Integrity

The musical performance is identical to the original recording.

Only the following changes were made:

1. The original file was divided into two MIDI files at **Bar 25 (25:01:000)**.
2. **6WALTZ.MID** received an explicit **3/4 Time Signature** Meta Event.

All note events, note timing, velocities, durations, and musical performance remain unchanged.

---

# Archive Note

The original **6MISC2.MID** has been superseded by **6MISC3.MID** and **6WALTZ.MID**.

Both replacement files preserve the complete musical content of the original while providing consistent time signatures and improved compatibility with analysis tools.

**The original 6MISC2.MID may be retained for historical reference or removed from the archive at the maintainer's discretion.**
