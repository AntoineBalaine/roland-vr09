# Reverse engineering the Touché / Lié link

Goal: find out, by capturing the actual MIDI traffic, what Expressive E's Lié software sends to
the Touché when editing its mapping, and what the Touché's two selector buttons send in each
mode — the same kind of experiment that found the VR-09's undocumented RQ1 support (see
`midi-capabilities.md`), aimed at a different device. Not started yet; this is the plan and the
background research, for picking the work back up.

## Why this needs the Mac, not this Linux box

Lié (Expressive E's configuration app for the Touché) has no Linux build. Its published system
requirements list macOS and Windows only, both as a plugin and as the standalone app. Wine was
considered and ruled out: running USB MIDI device access through Wine's driver translation layer
tends to be unreliable even when the app launches, and it would add a layer of uncertainty on
top of the thing we're actually trying to learn. The user has a Mac this can run on instead, and
will use Lié's standalone app, no DAW involved, one less layer to account for.

## Why this should be easier on Mac than the equivalent Linux experiment

macOS's native MIDI system, CoreMIDI, lets multiple applications observe the same MIDI port at
once. Unlike a Linux ALSA raw MIDI device (which `vr09.py` opens exclusively, locking out any
other reader), CoreMIDI has no single-reader lock, so a logging tool can tap the Touché's ports
without any virtual-passthrough workaround and without touching Lié's own connection at all.

## Tooling

Two options, either works, pick whichever is more convenient at the time:

- **ReceiveMIDI** — free, open source, command-line, cross-platform (macOS/Windows/Linux too).
  Install with `brew install gbevin/tools/receivemidi`. Confirmed usage:
  - `receivemidi list` — lists available MIDI ports.
  - `receivemidi dev "Touché" ts` — selects a port by a substring match on its name (the match
    doesn't need to be exact or case-sensitive) and prints a timestamp with every message.
  - It has a `syx` option for System Exclusive handling, but the exact output format for an
    *incoming* SysEx dump wasn't confirmed from the README alone — check `receivemidi --help`
    once it's installed, or just try it against the Touché and see what the SAVE SETUP capture
    looks like.
- **MIDI Monitor** (by Snoize) — free GUI app, the long-standing standard tool for this on Mac.
  Watch the Touché's source and destination ports, logs every message both ways with timestamps
  and SysEx shown in hex. Use this if ReceiveMIDI's SysEx output turns out to be awkward to read.

## What we actually know about the Touché/Lié relationship so far (from documentation, not yet
## verified by capture)

- Default CC assignment, 4 axes: CC16, 17, 18, 19 (standalone default; Lié can reassign in its
  MIDI Instrument View, and the mapping is pushed to the device with SAVE SETUP).
- The Touché has 6 banks of 4 presets (24 total) in its own internal memory, each storing a full
  mapping. Recallable by the two selector buttons with no computer connected at all, once
  programmed once via Lié.
- In Slave mode (Lié connected), the buttons keep their preset-stepping behavior *and* send
  CC80 (left) / CC81 (right) on every press.
- No documentation found confirming the Touché can *receive* an incoming Program Change to
  recall one of its 24 stored presets remotely — only the two physical buttons and Lié itself are
  documented as able to change the active preset.
- Each Hardware Preset can be configured (via Lié's Instrument View) to send a Program Change,
  with its own MIDI channel and bank select MSB/LSB, when that preset loads — this is the
  mechanism for the Touché to drive *other* hardware's preset changes, not for driving its own.

## Test sequence, once logging is running

1. Open Lié standalone, Touché connected (Slave mode).
2. Remap one axis to a specific, deliberately unusual CC number and hit SAVE SETUP. Look for a
   SysEx dump in the log around that action.
3. With Touché still in Slave mode, press the left selector button once. Confirm CC80 appears
   (per the documentation above) and note anything else that comes with it.
4. Quit Lié so the Touché drops to Stand-alone mode, nothing connected on the software side.
   Press the buttons again. See whether anything is sent at all with no software running — this
   answers the open question above about whether preset recall ever produces outgoing traffic we
   could key off of, or whether it's purely internal to the device.

## Open questions this should answer

- The exact SysEx format Lié uses to write a mapping to the Touché (would open the door to
  scripting mapping changes outside Lié, the same way DT1/RQ1 opened up the VR-09).
- Whether anything distinguishes which of the 24 stored presets is active, observable over MIDI,
  which would make it possible to react to a preset change in our own software even in
  Stand-alone mode.
- Whether CC80/81 in Slave mode are reliable enough to key custom behavior off of (e.g.
  triggering a VR-09 scene change alongside a Touché preset change) — this part doesn't need the
  SysEx reverse engineering at all, it should already work today if confirmed.
