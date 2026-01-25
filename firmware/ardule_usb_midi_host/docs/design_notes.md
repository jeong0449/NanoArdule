# Ardule USB MIDI Host – Design Notes

Date: 2026-01-26

---

## 1. Purpose

This document records the design decisions, failed attempts, and final conclusions reached during the development of **Ardule USB MIDI Host**.

Rather than focusing on features alone, it aims to preserve:

* why certain problems appeared,
* which approaches were insufficient,
* and which design principles ultimately proved effective.

---

## 2. Original goals

* Convert USB MIDI input into stable DIN MIDI output
* Provide a reliable MIDI input path for Nano Ardule MIDI Controllers
* Maintain zero‑perceptible latency during live performance

---

## 3. Observations about USB‑MIDI handling

### 3.1 Characteristics of USB Host operation

* MAX3421E‑based USB Host Shields depend heavily on polling
* Reduced frequency of `Usb.Task()` calls immediately leads to input latency

### 3.2 USB‑MIDI Event Packet structure

* Data received via `RecvData()` is a USB‑MIDI Event Packet
* The first byte is a header (CIN), not a MIDI status byte
* MIDI message length cannot be inferred safely without considering CIN

Conclusion:

> **USB‑MIDI looks like MIDI, but it is not MIDI.**

---

## 4. Problems introduced by adding an LCD

### 4.1 Symptoms

* Noticeable delay when playing notes with a 20×4 I2C LCD connected
* Immediate recovery of responsiveness when the LCD was removed

### 4.2 Early assumptions

* I2C clock speed issues
* Inefficient LCD library implementation

These were partially true, but not the root cause.

---

## 5. Root cause analysis

* LCD updates require I2C transfers that block the CPU
* While updating the LCD, USB polling is delayed
* USB‑MIDI input timing degrades as a direct result

In short:

> **The LCD became an enemy of real‑time USB host processing.**

---

## 6. Approaches that failed

### 6.1 Throttling LCD updates

* Limiting refresh rates to 5–10 Hz
* Reduced I2C traffic, but latency during active playing remained

### 6.2 Partial LCD updates

* Updating only modified rows
* Further reduction of I2C traffic, but USB polling interference persisted

Key lesson learned:

> **In real‑time paths, partial reduction is often insufficient; complete removal is required.**

---

## 7. Final solution: freeze LCD during performance

### 7.1 Core idea

* Do not touch the LCD while MIDI events are arriving
* Resume LCD updates only after a defined idle interval (e.g., 500 ms)

### 7.2 Implementation outline

* Record the timestamp of the last MIDI event
* Compare it with the current time to detect active vs. idle states
* Allow LCD updates only in the idle state

### 7.3 Results

* I2C traffic during performance: zero
* USB polling frequency fully restored
* Playing responsiveness comparable to running without any LCD

---

## 8. Design principles derived

This subproject reinforced the following principles:

1. **Real‑time paths and UI paths must be strictly separated.**
2. In real‑time paths, delays, I2C, and debug output are all liabilities.
3. UI elements are observers, not participants, in real‑time processing.

---

## 9. Meaning within the Nano Ardule ecosystem

Ardule USB MIDI Host:

* Extends Nano Ardule’s reach into the USB MIDI domain
* Does not replace or duplicate Nano Ardule’s core functionality

It serves as a **gateway between the USB world and the Nano Ardule MIDI domain**, enabling Nano Ardule’s processing capabilities to be applied to modern USB MIDI devices.

---

## 10. Possible future improvements (notes)

* SysEx streaming pass‑through
* Filtering of MIDI Clock / Active Sensing
* Compile‑time option to completely disable LCD support
* Minimal LED‑based feedback instead of LCD
* Comparative tests on faster MCUs (UNO R4, Nano Every)

---

## 11. Closing remarks

This side project demonstrated how easily real‑time behavior can be compromised in small MCU environments.

More importantly, it clarified which elements truly belong in the real‑time path—and which do not.

The lessons learned here will directly inform future Nano Ardule designs and extensions.
