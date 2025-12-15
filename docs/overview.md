# Introducing the Ardule Ecosystem

The Ardule project began as an effort to repurpose a **SAM9703-based sound daughterboard** embedded in a Korean-style arranger module that also functioned as a MIDI interface, communicating with a PC via serial connection and dedicated proprietary software.  
This device, acquired by chance, was effectively unusable without its original software. As a first DIY step, the internal circuitry was modified so that **the MIDI signal received via the 5-pin DIN connector was opto-isolated and converted into a UART-compatible TTL-level serial signal before being fed into the SAM9703 board**. This modification made it possible to hear the module’s sound using a PC-based sequencer or a keyboard controller.

Soon after, the desire arose to gain more expressive and flexible control over the module without relying on a PC. This led to the development of an independent DIY device that receives MIDI signals from a keyboard or PC, forwards them to the sound module, and allows control over features such as program changes, layering, and splits, while providing a small LCD display. Built around an Arduino Nano–compatible board, this DIY unit was named the **Nano Ardule MIDI Controller**.  
The name *Ardule* is derived from *Arduino + Module*, and also echoes the French word *arduous*, meaning “difficult.” The ultimate goal was to add support for a microSD card to save and load settings, as well as to enable playback of **Type 0 MIDI files**.

The next challenge was to add a **drum pattern player** function. However, the limited capabilities of the Arduino Nano made this extremely difficult, especially when combined with the already implemented controller features. As a result, an **Arduino Nano Every**, with significantly higher hardware capabilities, was adopted to build a dedicated drum pattern player and Type 0 MIDI file player. This device became the **(Nano) Ardule Drum Pattern Player**, often referred to simply as **“Ardule.”** In essence, the aim was to create a system capable of providing drum accompaniment or other backing parts suitable for live performances by amateur bands.

With the exception of the MCU itself, the surrounding hardware of the Nano Ardule MIDI Controller and the Nano Ardule Drum Pattern Player is completely identical. Both use the same MIDI IN/OUT circuitry, push buttons, rotary encoders, and a 1602 LCD. The two devices are differentiated solely by firmware; the Arduino “Nano” can simply be swapped in its socket according to the intended use.

What makes the Nano Ardule Drum Pattern Player distinctive as a MIDI file player is that **it plays MIDI files through a bare-metal implementation that avoids dedicated MIDI libraries, instead performing direct SMF parsing and real-time event scheduling**.  
To implement the drum pattern player, MIDI files had to be segmented into **2-bar patterns**, and enabling the Arduino to recognize and replay these patterns efficiently and seamlessly proved to be a highly challenging task. To address this, several custom data and information schemes were developed, including **ADT, ADP, ARR, and ADS**. All of these tasks are implemented to run on a PC using **Python**.

- **ADT (Ardule Drum Text):** A human-readable, text-based format for editing and defining 2-bar drum patterns.  
- **ADP (Ardule Drum Pattern):** A compact binary format converted from ADT for efficient playback on Arduino hardware.  
- **ARR (Ardule Arrangement):** A pattern chain format that defines the song structure by sequencing multiple drum patterns.  
- **ADS (Ardule Drum Stream):** A precompiled streaming format generated from ARR for seamless, uninterrupted playback on the Nano Ardule Drum Pattern Player.

While grid-based drum pattern formats are widely used, **ADT distinguishes itself by being a human-readable, semantically expressive text format designed specifically for portable, embedded playback and long-term pattern reuse**.

**APS (Ardule Pattern Studio)** is a PC-based tool for editing drum patterns, managing arrangements, and compiling ADT, ADP, ARR, and ADS data for the Ardule system, bridging human-readable pattern design and efficient embedded playback.  
The Ardule Drum Pattern Player currently supports **ADT and ADP** formats for pattern playback, as well as **Standard MIDI Files** for full-song playback. Authoring is performed entirely on the PC using APS, and future development will add support for **ARR arrangements** and deeper integration with **APS-based workflows**.

Many loopers and practice amplifiers include built-in drum pattern players; Ardule already provides this functionality while supporting a far larger and more extensible pattern library. The available patterns can be expanded indefinitely through the user’s own creativity.

The entire process, from circuit design to software development, was carried out with the assistance of **ChatGPT as a collaborative tool**. If the opportunity arises, I would like to design and fabricate a dedicated PCB.  
**I hope this project can contribute, even in a small way, to your musical creativity and DIY journey.**
