# Roland VR-09 — Registration/Scene Switching via MIDI

Research notes on whether and how the Roland VR-09 (V-Combo organ/keyboard) can have its
Registration banks (scenes) switched remotely via MIDI.

## TL;DR

- Ordinary MIDI **Program Change** and **Bank Select** messages **cannot** switch Registrations
  on the VR-09. They are explicitly **not received by the keyboard sound generator** — only by
  the separate GM2 accompaniment engine (see below).
- The only documented path to changing what the keyboard part plays is Roland's proprietary
  **SysEx DT1** ("Data Set 1") command, which writes directly to addresses in the VR-09's
  internal Parameter Address Map.
- No existing public project (that we found) implements live DT1-based Registration switching.
  Everything found either parses *outgoing* SysEx from the unit's knobs/drawbars, or edits
  Registration files offline.
- An undocumented **RQ1** ("Request Data 1", command ID `11H`, sibling to DT1's `12H`) exists on
  this hardware even though it isn't in the published chart, and it reads back any block of the
  Parameter Address Map. See the Results section below.

## Background: two sound generators

Per Roland's own MIDI Implementation document (local copy: `docs/VR-09_VR-730_MIDI_Implementation.pdf`):

> "The VR (VR-09 or VR-730) contains two sound generators: one for accompaniment (GM2) and one
> for keyboard performance."

- **Keyboard sound generator** — produces the VR-09's own organ/EP/synth voices, the ones your
  Registrations (scene slots) actually recall. Does **not** respond to Program Change or Bank
  Select. Roland's own doc states plainly under the Program Change section: *"Not Received in
  keyboard part. Specification of the tones used by keyboard parts is accomplished using System
  Exclusive messages."*
- **GM2 sound generator** — a fully separate, standard General MIDI 2 synth engine (128 GM
  programs + drum kits), meant for accompaniment/backing use. **Is** reachable via ordinary
  Program Change and Bank Select, but it's a totally different, generic sound set — not a
  reduced version of the VR-09's own tones, and not your saved Registrations.

Which generator an incoming MIDI channel talks to is controlled by the **MIDI IN Mode** setting
on the unit (Mode 1 / Mode 2 / Keyboard — see p.1 of the implementation doc for the channel
routing table).

When you manually recall a Registration on the unit itself, the VR-09 *transmits* a Program
Change message out over MIDI on its Control Channel (so other gear can follow along) — but it
never *listens* for one coming in to do the reverse.

## The SysEx / DT1 route

- **DT1 ("Data Set 1")** is Roland's proprietary SysEx command for writing to an internal memory
  address: `F0 41 10 <model ID> 12H <address> <data...> <checksum> F7`.
- The **Parameter Address Map** (p.11 of the implementation doc) lists addresses for Upper Part,
  Lower Part, Organ Part, Drum Part, etc. Each part has `Tone Bank Select MSB`, `Tone Bank Select
  LSB`, and `Tone Program Number` fields among others.
- There is **no single documented address that means "recall Registration N."** A Registration
  is a bundle of per-part settings, not one scalar value. To reproduce what recalling a
  Registration does, you'd need to write to each relevant part's addresses individually.
- Checksum is computed by summing address + data bytes, taking mod 128, and subtracting the
  remainder from 128 (worked example on p.14 of the doc).

### Bank Select / Program Number primer

For anyone picking this up fresh: MIDI Program Change alone only selects among 128 sounds (1
byte). Bank Select (a Control Change message, split into MSB on controller 0 and LSB on
controller 32) lets you first choose a "page" of 128 sounds before Program Change picks the
specific one within it — together addressing up to 16,384 banks. The VR-09's Parameter Address
Map stores these same three values (Bank MSB / Bank LSB / Program Number) per part, but since
Program Change and Bank Select aren't received on the keyboard part, you write to those memory
addresses directly via DT1 instead.

## The undocumented RQ1 possibility

Roland's shared "Roland Exclusive" SysEx format pairs DT1 (write, `12H`) with **RQ1** ("Request
Data 1", `11H`) on much of their other hardware — RQ1 asks the device to transmit back the data
at a given address instead of writing it. The VR-09's implementation chart doesn't document RQ1
at all, but that's not proof it's unsupported; it may simply be undocumented because it wasn't
meant to be user-facing. Neither of the GitHub projects below has tested this.

**Suggested first experiment:** send `F0 41 10 62 11 <address> <size> <checksum> F7` (swapping
DT1's `12H` for RQ1's `11H`) targeting a known address from the Parameter Address Map, and see
if the unit replies with a DT1 message echoing data back. If it works, it would let us read
Registration state directly instead of reconstructing it by ear.

## Suggested process (if RQ1 doesn't pan out)

1. **Test RQ1** as above — cheapest possible win, do this first.
2. **Passive listen** — connect a MIDI monitor (MIDI-OX, or a quick Python script with
   `mido`/`python-rtmidi`) and watch for any traffic the VR-09 emits on its own while
   manually operating it (recalling Registrations, moving drawbars), in case there's
   undocumented traffic beyond the single Program Change on the Control Channel.
3. **Manual DT1 testing** — construct individual DT1 writes against addresses from the
   Parameter Address Map (start with something simple and audible, e.g. Upper Part Tone Bank
   Select MSB/LSB + Program Number), confirm by ear / front panel display.
4. **Build out part-by-part** — repeat for Upper, Lower, Organ parts to reconstruct everything
   that changes when a Registration is recalled.
5. **Document as a lookup table** — map each saved Registration slot to a batch of DT1 messages
   that reproduce it, since the VR-09 won't do that translation over MIDI itself. The
   `vr09-tools` project below may have already done some of the legwork on how Registration data
   is encoded in `.UPG` files, worth checking before doing this from scratch.

## Results (tested over USB on a VR-09 in MIDI IN Mode 2)

Scene switching from dumps works for the sound and the part list, using `vr09.py`. A dump is a
snapshot of the keyboard's parameter values, taken after recalling a Registration with its panel
button. A recall writes a dump's values back, so the keyboard sounds like that Registration. The
keyboard's own Registrations cannot be selected, read or edited over MIDI. See
`docs/midi-capabilities.md` for details.

```
vr09.py dump NAME     read all blocks into dumps/NAME.json
vr09.py recall NAME   write dump NAME to the keyboard without reading it first (about 0.15 seconds)
vr09.py diff A B      list the differences between two dumps
vr09.py watch         print every change made on the panel as it happens
```

- RQ1 works: `F0 41 10 62 11 <address 3 bytes> <size 3 bytes> <checksum> F7` gets a DT1 reply.
  The synth section answers the same request with model ID `00 00 71` and four-byte addresses.
- The unit also sends a DT1 by itself when a panel control changes, so `watch` could also listen
  passively.
- Reads accept a whole block, but writes must start at a parameter's own address. Addresses
  marked `#` in the map cannot start a message: the reverb level is written with the reverb type
  (`00 00 00`, two bytes), and the bank bytes with the tone number (offset `00 01`, three bytes).
  The same holds for the bank and program bytes of the Synth Set parts (offset `00 06`).
- A Registration is not stored as one value. Recalling one rewrites the tone numbers, the section
  MUTE flags, the organ drawbars and about twenty values of the System block. Recalling a dump
  writes those values and reproduces the sound and the list of parts shown on the screen.
- The Registration title, number and button LEDs are not readable or writable. A scan of the
  first 16 groups of 128 x 128 addresses found no value that changes with the Registration
  number, so the screen keeps showing the previous title after a recall.
- The scan found eight part slots outside the map (`01 00`, `01 10`, `01 12`, `01 20`, `01 21`,
  `01 22`, `01 30`, `01 51`). They are part of the dumps but were identical in the Registrations
  we compared.
- Known leftovers after a recall: the bank LSB of the first synth part in Registration 3 reads
  back as 0 instead of 64, and the octave shift of the upper synth part in Registration 4 reads
  back as 52 instead of 64. The sound is unaffected as far as we heard.
- The unit stays silent for a moment after a Registration recall, so reads retry on an empty
  reply. Sending thousands of reads to undefined addresses made the unit stop answering until it
  was restarted, so keep scans inside the documented address groups.

## Connecting hardware

The VR-09 has a USB Type B "USB COMPUTER" port that is **class-compliant** — no drivers needed,
works directly with a standard USB A-to-B cable on Windows/Mac. No separate MIDI interface box
is required. From a phone (iOS/Android), the same cable works via a USB OTG adapter (Lightning/
USB-C camera adapter for iPhone, USB-C OTG for Android) — the phone acts as USB host, same as a
laptop. Traditional 5-pin MIDI In/Out ports also exist on the back panel but aren't needed given
the USB connection.

## References

- [Roland VR-09/VR-730 MIDI Implementation (official PDF)](https://static.roland.com/assets/media/pdf/VR-09_VR-730_MIDI_Imple_eng01_W.pdf) — local copy in `docs/`
- [vcombo-sysex-translator (GitHub)](https://github.com/mfisher87/vcombo-sysex-translator) — translates *outgoing* SysEx from V-Combo drawbars/knobs into MIDI CC; does not attempt readback or Registration control
- [vr09-tools (GitHub, mirrored from Google Code)](https://github.com/wesgarland/vr09-tools) — offline toolkit for editing `.UPG` Registration files; no live MIDI
- [Roland VR-09b registration change — midi.org community thread](https://midi.org/community/getting-started-with-midi-1/roland-vr-09b-registration-change) — user attempted `F0 41 10 62 12 B4 00 01 FF F7`, unresolved
- [Roland VR09B Registration Bank Switching via External MIDI — Keyboard Forums](https://www.keyboardforums.com/threads/roland-vr09b-registration-bank-switching-via-external-midi.36787/) — confirms long-standing complaint, no working solution posted
- [MIDI (IN) Receive Program-Change switching Registrations? — Roland Clan Forums](https://forums.rolandclan.com/viewtopic.php?t=58060)
