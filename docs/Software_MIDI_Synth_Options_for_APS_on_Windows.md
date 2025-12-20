# Software MIDI Synth Options for APS on Windows

Version: 2025-01  
Applies to: APS v0.27+

---

## Change Log

### 2025-01
- **Clarified VirtualMIDISynth usage conditions**
  - Added explicit warning about first-note and count-in latency when APS opens VirtualMIDISynth directly.
  - Reframed VirtualMIDISynth as a *conditional* recommendation rather than a default replacement.
- **Documented routing-dependent behavior**
  - Distinguished between direct APS → VirtualMIDISynth usage and routed usage via loopMIDI + persistent host.
- **Updated recommended workflow**
  - Emphasized stability-first approach: Microsoft GS for verification, routed software synths or hardware modules for regular use.
- **Added design philosophy note**
  - Clarified that APS deliberately avoids device-specific warm-up or port-lifecycle hacks to preserve stability.
- **Aligned documentation with real-world testing**
  - Reflected observed behavior on Windows WinMM with VirtualMIDISynth and Microsoft GS Wavetable Synth.

---

## 1. Default Option: Microsoft GS Wavetable Synth

Windows includes a built-in General MIDI synthesizer called **Microsoft GS Wavetable Synth**.
It is available on all standard Windows installations and requires no additional setup.

APS can send MIDI output directly to this synth, making it the simplest possible starting point.

### Advantages
- Zero configuration
- Always present
- Useful for functional checks

### Limitations
- High latency
- Fixed sound set
- Limited audio quality

---

## 2. VirtualMIDISynth (Conditional Recommendation)

VirtualMIDISynth is a SoundFont-based MIDI synthesizer for Windows.

### Important Note

When APS opens VirtualMIDISynth **directly** as a MIDI OUT device,
some systems may experience:
- First note drop or delay
- Unstable count-in timing

This behavior originates from internal initialization in the synth and WinMM stack,
not from APS itself.

### Recommended Usage

**Stable:**
APS → loopMIDI → persistent host → VirtualMIDISynth

**Direct (use with caution):**
APS → VirtualMIDISynth

APS intentionally avoids internal workarounds that would compromise stability.

---

## 3. Falcosoft MIDI Player (Debugging Option)

Falcosoft MIDI Player provides:
- Visual MIDI inspection
- SoundFont playback
- Timing and controller analysis

Ideal for debugging APS output.

---

## 4. Recommended Workflow

1. Use Microsoft GS to verify APS output
2. Use loopMIDI + persistent host for software synths
3. Prefer hardware GM modules for timing-critical use

---

This document reflects real-world APS usage on Windows and supersedes earlier guidance.
