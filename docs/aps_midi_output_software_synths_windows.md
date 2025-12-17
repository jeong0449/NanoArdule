# Software MIDI Synth Options for APS on Windows

This document explains how **APS (Ardule Pattern Studio)** can use the **built-in Microsoft GS Wavetable Synth** on Windows by default, and introduces recommended alternatives for users who want better sound quality, flexibility, or debugging capabilities.

---

## 1. Default Option: Microsoft GS Wavetable Synth

### Overview

Windows includes a built-in General MIDI synthesizer called **Microsoft GS Wavetable Synth**. It is available on all standard Windows installations and requires no additional setup.

APS can send MIDI output directly to this synth, making it the **simplest possible starting point**.

### Characteristics

- Built into Windows (no installation required)
- General MIDI compatible
- Automatically available as a MIDI OUT device

### Advantages

- Zero configuration
- Always present on Windows systems
- Useful for quick functional checks

### Limitations

- Noticeable latency (not suitable for tight timing work)
- Fixed sound set (no SoundFont loading)
- Limited audio quality compared to modern alternatives
- Not suitable for detailed debugging or sound comparison

### When to Use

- First-time APS setup
- Quick confirmation that MIDI output works
- Non-critical listening

---

## 2. Why Consider Alternatives?

While Microsoft GS Wavetable Synth is convenient, APS users often want:

- Lower latency
- Better drum sounds (especially GM Channel 10)
- Custom SoundFonts (SF2)
- A workflow closer to using a hardware sound module

For these reasons, external software synthesizers are strongly recommended for regular APS use.

---

## 3. VirtualMIDISynth (Recommended Default Alternative)

### Overview

**VirtualMIDISynth** is a dedicated SoundFont-based MIDI synthesizer for Windows. It acts as a virtual replacement for a hardware GM sound module.

### Typical Routing

```
APS → loopMIDI → VirtualMIDISynth → Audio Output
```

### Strengths

- Very low latency compared to Microsoft GS
- Supports multiple SoundFont (SF2) files
- Stable GM / GS drum handling
- Runs quietly in the background (system tray)

### Ideal Use Case

- Daily APS pattern and chain playback
- Sound development without hardware modules
- Consistent, reliable MIDI monitoring

---

## 4. Falcosoft MIDI Player (Advanced / Debugging Option)

### Overview

**Falcosoft MIDI Player** is a full-featured MIDI player and analysis tool with an integrated SoundFont synthesizer.

### Typical Routing

```
APS → loopMIDI → Falcosoft MIDI Player → Audio Output
```

### Strengths

- Visual inspection of MIDI events
- Channel mute/solo and controller monitoring
- SysEx and timing analysis
- Easy SoundFont comparison

### Ideal Use Case

- Debugging APS output
- Verifying controller messages and timing
- Comparing SoundFonts and mappings

---

## 5. Comparison Summary

| Feature | Microsoft GS | VirtualMIDISynth | Falcosoft MIDI Player |
|------|---------------|------------------|----------------------|
| Built into Windows | Yes | No | No |
| Latency | High | Low | Low |
| SoundFont (SF2) | No | Yes | Yes |
| Background synth | Yes | Yes | No |
| MIDI analysis | No | No | Yes |
| Recommended for APS | Basic only | ★★★★★ | ★★★★ |

---

## 6. Recommended APS Workflow

1. **Start with Microsoft GS Wavetable Synth**
   - Confirm APS MIDI output works

2. **Switch to VirtualMIDISynth for regular use**
   - Better sound and timing
   - Closest experience to hardware GM modules

3. **Use Falcosoft MIDI Player when debugging**
   - Inspect events and controllers
   - Diagnose timing or mapping issues

A practical approach is to create multiple virtual MIDI ports using **loopMIDI**, and switch APS output ports as needed.

---

## 7. Conclusion

Microsoft GS Wavetable Synth provides a convenient baseline for APS on Windows, but it is best viewed as a **functional default**, not a long-term solution.

For serious APS work:

- **VirtualMIDISynth** is the recommended everyday software synth
- **Falcosoft MIDI Player** is an excellent companion tool for analysis and debugging

Together, these tools provide a flexible and powerful software-based alternative to hardware sound modules.

---

*This document is intended for inclusion in the APS documentation (doc/) within the GitHub repository.*

