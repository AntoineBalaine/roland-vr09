# What the VR-09 can be controlled with over MIDI

Findings from testing a VR-09 over USB in MIDI IN Mode 2, cross-checked with the MIDI
Implementation document (`docs/VR-09_VR-730_MIDI_Implementation.pdf`), including its
implementation chart.

## Loading a Registration

No single message loads a Registration. A scene switch is done by writing each parameter
with DT1, which `vr09.py recall NAME` does in about 0.15 s (66 messages, 2 ms apart).

What was ruled out:

- Program Change and Bank Select to the keyboard parts: the document says they are not
  received.
- Program Change, with and without Bank Select, on channel 16 (the control channel in
  Mode 2): tested, no parameter changed.
- The keyboard part's address space, first 16 address groups: scanned, no address follows the
  selected Registration number. The title, the number and the button LEDs therefore stay on
  the previous Registration after a recall.

What is still open:

- Other model IDs and the address groups above `0F`. Scanning undefined addresses made the unit
  stop answering until it was restarted, so this needs care.
- Loading Registrations from a USB memory stick (offline only, not live).
- The Roland app, see below.

## The Roland app: VR-09 Editor

- iPad only (the App Store lists iPadOS 8.0 or later). There is no Android version.
- Last version 1.1.0, from September 2017.
- It edits the organ and synth tones (drawbars, leakage, click, rotary speed, synth parameters,
  layers and splits). Neither Roland's product page nor the App Store page mentions selecting,
  recalling or saving Registrations.
- Connection: USB through the iPad camera adapter, or wireless with "Roland Wireless Connect",
  which needs a Roland WNA1100-RL (or ONKYO UWF-1) USB Wi-Fi adapter on the keyboard and a
  router with WPS.

Because the app does not claim to recall Registrations, capturing its messages is unlikely to
reveal a recall command. It might still reveal undocumented parameter addresses. A capture
needs something between the iPad and the keyboard, for example a Linux board acting as a USB
MIDI device (USB gadget mode, `f_midi`) that forwards and logs everything.

Sources: https://www.roland.com/CA/products/vr-09_editor/ and
https://apps.apple.com/app/id589704005

## Write rules for DT1

- One message writes one parameter. Gaps of 1 to 20 ms between messages all worked; no gap
  overflows the unit's buffer ("Midi buffer full") and most writes are lost.
- Addresses marked `#` in the map cannot start a message. The reverb level is written with the
  reverb type (`00 00 00`, two bytes), and the bank bytes with the tone number (offset `00 01`
  of a part, three bytes). The same holds for the Synth Set parts (offset `00 06`, three bytes).
- Writing a whole block as one message does not work: only some of its parameters are applied.
- Reads (RQ1) accept whole blocks.

## Capabilities

| Feature | Over MIDI | How |
|---|---|---|
| Tempo, clock sync | No | The chart marks Clock as transmitted only, when the Composer plays. The address map has no tempo parameter. |
| Rhythm start/stop | No | Only as a footswitch function. The function given to each pedal is writable (`00 00 4F`, `00 00 50`), but the pedal cannot be pressed over MIDI. |
| Rhythm volume | Yes | RHYTHM LEVEL, `00 00 25`. |
| Song volume | Yes | SONG LEVEL, `00 00 23`. |
| Drums | Partly | In Mode 2, channel 11 is the DRUM part: drums can be played from an external sequencer with its own clock. The kit is probably the tone number of the DRUM part (`01 41 01`), not tested. |
| Effect types and levels | Yes, live | DT1: reverb type and level, MFX type and level, delay type and level, overdrive, compressor, tone level, rotary speeds. |
| Organ drawbars | Yes, live | DT1, `02 00 03` to `02 00 0B` for the upper organ; the panel LEDs follow. |
| Per-channel controllers | Yes | CC91 reverb send, CC93 chorus send, CC71 to CC77 (resonance, release, attack, cutoff, decay, vibrato rate and depth), CC7 volume, CC10 pan. |
| Overall volume | Yes | CC11 on channel 16, like the expression pedal. |
| Panel changes | Transmitted | The unit sends a DT1 by itself when a panel control changes. |

## Channels in Mode 2

| Channel | Part |
|---|---|
| 1 | Piano Dual 2 (when a piano sound is on part 2) |
| 2 | Pedal |
| 3 | Lower |
| 4 | Upper |
| 11 | Drum |
| 16 | Control |
| 5 to 10, 12, 14, 15 | GM2 sound generator |
