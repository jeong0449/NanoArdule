# APS Drum Instrument Sets & Pad Mapping — Reference Specification

**Version:** v1.0
**Date:** 2026-02-09
**Status:** Reference / Implementation-level Specification

---

## 1. Scope and Purpose

This document defines the **reference drum instrument sets and pad mappings** used by APS-based editors and controllers.

It specifies:

* Canonical instrument groupings (categories)
* The *APS Default 12* instrument set
* The legacy UI instrument set
* The reference pad mapping for **AKAI MPK MINI (16 pads)**

This specification is **non-normative with respect to the ADT format**.
ADT intentionally defines *instrument slots* without binding them to concrete instrument identities.

---

## 2. Terminology

* **ADT**: Ardule Drum Track format
* **APS**: Ardule Pattern Studio
* **Instrument Slot**: A logical drum role defined in ADT (maximum 12)
* **Instrument Set**: A concrete assignment of musical instruments to slots
* **Pad Mapping**: Physical controller pad positions mapped to instruments

---

## 3. Instrument Categories

APS instruments are grouped by functional role rather than timbre or MIDI number.

| Category           | Description                                  |
| ------------------ | -------------------------------------------- |
| Core               | Timekeeping backbone, always preserved       |
| Fills / Transition | Drum fills and sectional transitions         |
| Rhythmic Perc      | Percussion directly shaping groove           |
| Color / FX         | Texture, accents, and decorative sounds      |
| Legacy / Optional  | Historically present or optional instruments |

---

## 4. Reference Instrument Sets

### 4.1 APS Default 12

The **APS Default 12** defines the canonical instrument set used by APS editors and StepSeq.

* Maximum of 12 instruments
* Always includes all *Core* instruments
* Forms the baseline for automatic row registration

### 4.2 Legacy UI Set

The **Legacy UI Set** documents instruments historically exposed in earlier APS grid-based UIs.

* Provided for backward reference only
* Not required to be supported by new controllers

### 4.3 MPK MINI Pad 16 Set

The **MPK MINI Pad 16 Set** defines a reference physical mapping for 4×4 pad controllers.

* Core instruments occupy the lower pad row
* Upper rows are organized by functional category

---

## 5. Reference Table

| Category           | Instrument     | Legacy UI Set | APS Default 12 | MPK MINI Pad 16 | Pad Location |
| ------------------ | -------------- | ------------- | -------------- | --------------- | ------------ |
| Core               | KK (36) KICK   | O             | O              | O               | Core         |
|                    | SN (38) SNARE  | O             | O              | O               | Core         |
|                    | CH (42) HH_CL  | O             | O              | O               | Core         |
|                    | OH (46) HH_OP  | O             | O              | O               | Core         |
| Fills / Transition | MT (47) TOM_M  | O             | O              | O               | Upper_1B     |
|                    | LT (45) TOM_L  | O             | O              | O               | Upper_1C     |
|                    | HT (50) TOM_H  | O             | O              | O               | Upper_2D     |
|                    | CR (49) CRASH  | O             | O              | O               | Upper_1A     |
|                    | RD (51) RIDE   | O             | O              | O               | Upper_1D     |
| Rhythmic Perc      | CL (39) CLAP   | O             | O              | O               | Upper_2A     |
|                    | TA (54) TAMB   |               | O              | O               | Upper_2B     |
|                    | CB (56) COWBL  |               | O              | O               | Upper_2C     |
| Color / FX         | RM (37) RIM    | O             |                | O               | Upper_3A     |
|                    | SH (82) SHAKR  |               |                | O               | Upper_3B     |
|                    | HW (76) WBLK_H |               |                | O               | Upper_3C     |
|                    | SP (55) SPLASH |               |                | O               | Upper_3D     |
| Legacy / Optional  | PH (44) HH_PED | O             |                |                 | —            |

---

## 6. Design Rationale (Informative)

* **Core instruments are immutable** and must always remain visible in StepSeq.
* **APS Default 12** balances expressive power with UI and hardware constraints.
* Pad layouts prioritize *physical playability* and *real drum-set ergonomics* over pitch ordering.

---

## 7. Versioning Policy

This specification follows independent semantic versioning.

* Minor versions: Instrument additions or reclassification
* Major versions: Structural or conceptual changes

---

## 8. References

* ADT v2.2 Specification
* APS User Manual
* AKAI MPK MINI Controller Documentation
