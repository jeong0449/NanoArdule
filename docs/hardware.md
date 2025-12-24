# Hardware

This document provides a minimal overview of the Nano Ardule hardware.
Only the wiring diagram, MIDI schematic, and pin mapping are described here.
For design rationale and firmware behavior, refer to the main README.

---

## Wiring Diagram

![Nano Ardule Wiring Diagram](./images/Nano_Ardule_Wiring_Diagram.svg)

---

## MIDI Interface Schematic

![MIDI Schematic](./images/MIDI_schematics.png)

---

## Notes on Special Pins

### D0 / D1 (RX / TX)

Pins **D0 (RX)** and **D1 (TX)** are used for **MIDI IN** and **MIDI OUT**.
On the classic Arduino Nano, these pins are shared with the USB serial interface used for firmware upload.

To avoid conflicts during upload, the MIDI connection to D0/D1 is routed through jumper headers:
- During firmware upload, the jumpers are disconnected
- After upload, the jumpers are reconnected for normal MIDI operation

This workaround is **not required** when using the **Arduino Nano Every**, as it uses a separate USB interface and does not share D0/D1 with USB serial communication.

### A6 (PART SELECT Button)

Pin **A6** is an **analog-input-only pin** and is therefore well suited for use as a button input.

Because A6 does not support the internal pull-up resistor, an **external pull-up resistor is required** when using this pin.

---

## Pin Mapping

| Arduino Pin | Function              | Description / Role                               |
|-------------|-----------------------|--------------------------------------------------|
| D0          | MIDI IN (RX)          | MIDI input (UART RX, jumper-isolated on Nano)    |
| D1          | MIDI OUT (TX)         | MIDI output (UART TX, jumper-isolated on Nano)   |
| D2          | Rotary Encoder CLK    | Rotation signal A (interrupt-capable)            |
| D3          | Rotary Encoder DT     | Rotation signal B (interrupt-capable)            |
| D4          | Encoder SW (Button)   | Rotary encoder push button input                 |
| D5          | MULTI Button          | Enter MULTI-CHANNEL mode                         |
| D6          | STOP / EXIT Button    | Exit edit mode or stop playback                  |
| D7          | SAVE / + Button       | Save current settings or increment value         |
| D8          | LOAD / − Button       | Load saved program or decrement value            |
| D9          | MIDI Activity LED     | Indicates MIDI IN / OUT activity                 |
| D10         | microSD CS            | SD card chip select                              |
| D11         | microSD MOSI          | SPI data output                                  |
| D12         | microSD MISO          | SPI data input                                   |
| D13         | microSD SCK           | SPI clock                                        |
| A0          | Part A LED            | Part A active indicator                          |
| A1          | Part B LED            | Part B active indicator                          |
| A2          | Drums LED             | Drums mode indicator                             |
| A3          | PLAY / PAUSE Button   | MIDI playback control                            |
| A4          | LCD SDA               | I2C LCD data                                     |
| A5          | LCD SCL               | I2C LCD clock                                    |
| A6          | PART SELECT Button    | Analog input only, external pull-up required     |

---
