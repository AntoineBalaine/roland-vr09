# Live CC modulation targets (for the Touché or any CC controller)

Pulled from `midi-capabilities.md` and the implementation document's per-message sections (the
ones that explicitly tag a message `[VR]` for the keyboard part, not just the summary chart at
the back, which was harder to read cleanly off the page image and is not relied on here).

None of these have been tested as live incoming Control Change yet — everything verified so far
in this project went through DT1/RQ1 (`vr09.py`), not plain CC. Every row below needs to be
double-checked by hand: send the CC from the Touché (or any controller) on the right channel for
Mode 2 (1 Piano Dual 2, 2 Pedal, 3 Lower, 4 Upper, 16 Control) and confirm with `vr09.py watch`
whether the corresponding address actually moves.

| CC# | Name | Tagged `[VR]` in the doc? | Status |
|---|---|---|---|
| 7 | Volume | yes | needs double-check |
| 10 | Pan | yes | needs double-check |
| 11 | Expression | yes | needs double-check (also usable on channel 16 as overall volume, see below) |
| 64 | Hold 1 (sustain) | yes | needs double-check |
| 65 | Portamento on/off | yes | needs double-check |
| 5 | Portamento time | yes | needs double-check |
| 66 | Sostenuto | yes | needs double-check |
| 67 | Soft | yes | needs double-check |
| 71 | Resonance | yes | needs double-check |
| 72 | Release time | yes | needs double-check |
| 73 | Attack time | yes | needs double-check |
| 74 | Cutoff | not seen tagged `[VR]` in the text we read, chart marks it ambiguously | needs double-check, may be GM2-only |
| 75 | Decay time | listed under "synth sound shaping" in `midi-capabilities.md`, tag not confirmed | needs double-check |
| 76 | Vibrato rate | same as above | needs double-check |
| 77 | Vibrato depth | same as above | needs double-check |
| 91 | Reverb send | documented per-part | needs double-check |
| 93 | Chorus send | documented per-part | needs double-check |
| — | Pitch bend | yes | needs double-check |

Channel 16 (Control, in Mode 2) also documents CC11 as overall volume, same as the expression
pedal — separate from per-part CC11 on channels 1-4.

## How to double-check one

1. Put the unit in MIDI IN Mode 2 (see `midi-capabilities.md` for the Identity Request check).
2. Run `vr09.py watch` in one terminal.
3. From the Touché (or any controller/DAW), send the CC in question on the target part's channel
   (1, 2, 3 or 4 — see the Channels in Mode 2 table).
4. If an address in `watch`'s output changes while you move the control, mark the row above
   Verified and note the address; if nothing changes, mark it Not received.

## Touché wiring

The Touché's MIDI out is a 3.5 mm TRS jack with a 5-pin DIN breakout cable included. Plug that
into the VR-09's physical MIDI In port on the back panel — this is independent of the USB
connection to the computer, so both can be connected to the keyboard at once. Which CC number
each of the Touché's four axes (press, two tilt directions, lift) sends is configured in
Expressive E's Lié software and stored in the Touché's own memory.
