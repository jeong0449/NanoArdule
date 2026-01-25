# Ardule USB MIDI Host

Date: 2026-01-26

---

## 1. Overview (What this is)

**Ardule USB MIDI Host** is a **companion side project** within the Nano Ardule ecosystem.

Its purpose is to receive **USB MIDI devices** (such as USB MIDI keyboards) using an Arduino UNO with a USB Host Shield (MAX3421E), and to convert them into a **standard DIN 5-pin MIDI output (31,250 bps)** in a reliable and latency-safe manner.

This firmware is **not** a Nano Ardule Controller or Player by itself. Instead, it serves as a dedicated **USB MIDI ingress**, allowing Nano Ardule systems to interact with the USB MIDI world.

---

## 2. Why this exists

* Arduino Nano–class boards cannot act as USB hosts.
* Nano Ardule MIDI Controllers are designed around DIN MIDI input.
* To use modern USB MIDI keyboards with Nano Ardule, a stable USB-to-DIN MIDI front-end is required.

This project was created to fill that role cleanly, without overloading the Nano Ardule Controller with USB host responsibilities.

---

## 3. Hardware configuration

* Arduino UNO
* USB Host Shield (MAX3421E based)
* USB MIDI keyboard
* DIN 5-pin MIDI OUT

Key points:

* DIN MIDI OUT uses **hardware serial TX (D1) at 31,250 bps**
* Downstream devices (including Nano Ardule) are assumed to use **opto-isolated MIDI IN**

---

## 4. Key technical points

* `USBH_MIDI::RecvData()` returns a **USB-MIDI Event Packet (4 bytes)**
* `msg[0]` is a **USB-MIDI header (including CIN)**, not a MIDI status byte
* MIDI message length must be determined using the **CIN / status combination**
* SysEx messages (CIN 0x4 / 0x6 / 0x7) are currently ignored
* DIN MIDI data is forwarded directly, without generating running status

---

## 5. LCD and latency problem (important)

When a 20×4 I2C LCD was added, **noticeable performance degradation** during live playing was observed.

Summary:

* USB Host Shields rely heavily on frequent polling via `Usb.Task()`
* I2C LCD updates consume CPU time and block USB polling
* Throttling LCD updates alone was insufficient to eliminate latency

Final solution:

> **Completely disable LCD updates while MIDI events are active,
> and resume LCD updates only after a defined idle period.**

This approach reduces I2C traffic to zero during performance and restores responsiveness comparable to running without an LCD.

---

## 6. Relationship to Nano Ardule

* This firmware is not part of the Nano Ardule core
* It acts as a **USB MIDI ingress module** placed in front of the Nano Ardule MIDI Controller
* Its role is to deliver clean, timing-safe MIDI data so that Nano Ardule can focus on processing (layering, remapping, filtering)

---

## 7. Current status

* Single USB MIDI device supported
* Stable enough for live performance
* Designed specifically as a companion to Nano Ardule

Future separation into a standalone project remains possible, but the current intent is to keep it as a side branch of the Nano Ardule ecosystem.
