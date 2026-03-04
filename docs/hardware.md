# Hardware

This document provides a minimal overview of the Nano Ardule hardware.
Only the wiring diagram, MIDI schematic, and pin mapping are described here.
For design rationale and firmware behavior, refer to the main [`README`](../README.md).

---

## Wiring Diagram

<img src="../images/Nano_Ardule_Wiring_Diagram.svg" width="600" alt="Nano Ardule Wiring Diagram">

---

## MIDI Interface Schematic

<img src="../images/MIDI_schematics.png"  width="600" alt="MIDI Interface Schematic">


---

## Notes on Special Pins

### UART RX/TX and Jumper Isolation

Pins **D0 (RX)** and **D1 (TX)** are used for **MIDI IN** and **MIDI OUT**.
On the classic Arduino Nano, these pins are shared with the USB serial interface used for firmware upload.

To avoid conflicts during upload, the MIDI connection to D0/D1 is routed through jumper headers:
- During firmware upload, the jumpers are disconnected
- After upload, the jumpers are reconnected for normal MIDI operation

This workaround is **not required** when using the **Arduino Nano Every**, employs a separate USB interface and does not share D0/D1 with USB serial communication.

### A6 (PART SELECT Button)

Pin **A6** is an **analog-input-only pin** and is therefore well suited for use as a button input.

Because A6 does not support the internal pull-up resistor, an **external pull-up resistor is required** when using this pin.

---

## Pin Mapping

| Arduino Pin | MIDI Controller | Drum Pattern Player |
|------------|----------------|---------------------|
| D0 | MIDI IN (RX) | - |
| D1 | MIDI OUT (TX) | - |
| D2 | Rotary Encoder CLK | - |
| D3 | Rotary Encoder DT | - |
| D4 | Encoder SW | - |
| D5 | MULTI Button | INTERNAL Pattern Mode (long press)|
| D6 | STOP / EXIT Button | - |
| D7 | SAVE / + Button | STEP + |
| D8 | LOAD / − Button | STEP − |
| D9 | MIDI Activity LED | - |
| D10 | microSD CS | - |
| D11 | microSD MOSI | - |
| D12 | microSD MISO | - |
| D13 | microSD SCK | - |
| A0 | Part A LED | Status LED |
| A1 | Part B LED | Status LED |
| A2 | Drums LED | Mode / Activity LED |
| A3 | PLAY / PAUSE Button | - |
| A4 | LCD SDA | - |
| A5 | LCD SCL | - |
| A6 | PART SELECT Button | Genre / Sort / Function (long press)|

---

## Nano Ardule Hardware Prototype

<img src="../images/Nano_Ardule.png"  width="600" alt="Nano Ardule prototype enclosed in a plastic case">

---

## Post-PC900 MIDI IN (6N138 Replacement Circuit)

The original design used the **Sharp PC900 opto-isolator**, which was commonly found in early MIDI interfaces.  
Unfortunately the PC900 has become increasingly difficult to source. For new builds we recommend using the widely available **6N138 optocoupler** instead.
For reference, see the SparkFun MIDI Shield schematic using the 6N138 optocoupler:

https://cdn.sparkfun.com/datasheets/Dev/Arduino/Shields/Midi_Shieldv15.pdf

However, the 6N138 **is not a drop-in replacement** for the PC900.

Unlike the PC900, the 6N138 uses a **photodarlington output stage** which produces slower signal edges.  
To ensure reliable UART reception at the MIDI baud rate (31,250 bps), an additional **Schmitt trigger buffer** should be used.

In this design the spare gates of a **74HC14** are used to clean up the signal.

### Recommended signal chain

````
MIDI IN → 6N138 → pull-up resistor → 74HC14 → 74HC14 → MCU RX
````

Using **two cascaded Schmitt trigger gates** is recommended:

* First gate sharpens the slow edge from the optocoupler
* Second gate restores polarity and further cleans the signal

This produces a very stable logic-level waveform for the microcontroller UART.




