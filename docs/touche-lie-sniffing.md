# Reverse engineering the Touché / Lié link

Goal: find out, by capturing the actual MIDI traffic, what Expressive E's Lié software sends to
the Touché when editing its mapping, and what the Touché's two selector buttons send in each
mode — the same kind of experiment that found the VR-09's undocumented RQ1 support (see
`midi-capabilities.md`), aimed at a different device. The first capture session has been done on
the Mac, and its results are in the "Findings" section below; the rest of this document is the
original plan and background research.

## Findings from the first capture session (Mac, Lié standalone, Touché in Slave mode)

Because the goal behind all of this is to switch VR-09 scenes from the Touché, the most useful
result is the first one: the Touché's two selector buttons already send everything we need, and
no knowledge of the Lié protocol is required for that.

### What the Touché sends (confirmed by capture)

- The four axes send CC16, CC17, CC18 and CC19 on channel 1, which matches Expressive E's
  documented defaults.
- The left selector button sends CC80 and the right selector button sends CC81, on channel 1.
  Lié's own MIDI display names them General Purpose 5 and General Purpose 6.
- Because every press sends two messages, a value of `0` first and a value of `127` about 120 ms
  later, any code that reacts to these buttons must act on only one of the two, otherwise each
  press would switch the scene twice. Reacting to `127` is the better choice, since `0` arrives
  at the instant of the press, before we know that the press is complete.
- The wheel of the controller sent nothing over MIDI during the session, so it either has no
  MIDI output or it needs a mode that we did not enter.
- The Touché shows up as two CoreMIDI sources: "TOUCHE Main Port", which carries the CCs above,
  and "TOUCHE Control Port", which carries SysEx.

### What the Control Port carries (observed, not decoded)

All of these start with `F0 00 21 26`, the Expressive E manufacturer ID.

- When Lié opens, the Touché sends `F0 00 21 26 04 0E 46 F7` and then a 29-byte message,
  `F0 00 21 26 04 01 1D 01 03 00 02 00 00 04 0E 07 0B 05 0B 0A 0B 54 4F 55 43 48 45 00 F7`.
  The second message contains the ASCII string `TOUCHE`, and its byte after `04 01` is `1D`,
  which equals its own length of 29. We therefore suspect it is a device announcement with a
  length field, but we have not verified this.
- Lié sends `F0 00 21 26 7F 01 1B F7` to the Control Port every 250 ms, for as long as it is
  connected. We believe it is a heartbeat, because it never changes and no reply was seen. The
  `7F` in the position where the Touché's own messages have `04` resembles a broadcast address,
  but this is a guess.
- Editing a preset inside Lié sends nothing to the Touché, because the edits only live on the
  software side. Loading a hardware preset, however, does send a full configuration, as the
  next section describes.

### What loading a hardware preset sends (second capture session)

Because the MIDI Monitor spy driver shows what Lié sends to the Touché, we captured the load
of two Roland System-8 hardware presets, "A5" and "B1". Every message below is addressed to
"TOUCHE Control Port".

- **SysEx configuration, group `03` (per sensor, indexes 0 to 7).** Each sensor receives a
  `16` message in two halves (offsets `00` and `40`, 64 entries each, every value written
  twice), followed by short `0F`, `10`, `09` and `06` messages. In the default case the table
  is the identity `00 01 02 … 7F`, which corresponds to the `Linear` curve with its
  `function0…127` values in the `.tem` file. The two presets differ in the curve tables of
  some sensors and in a few parameter bytes, so this group is preset-specific.
- **SysEx configuration, group `05` (per axis, indexes 0 to 3).** Each axis receives a 184-byte
  `16` table and the messages `0F`, `15`, `09` and `06`. These were byte-for-byte identical
  in both presets, so we believe this group is fixed. The value in `05 0F 00 <axis> <n>` was
  0, 1, 3, 2 for axes 0 to 3, which matches the sensor indexes of macros 16 to 19 in the
  `.tem` files (sensors 0, 1, 3 and 2).
- **A short tail**, `7F 0D 48`, `7F 09 41 00 01` and `7F 0F 49`, which we suspect applies or
  commits the configuration. Lié then sends the whole group `03` and `05` set a second time.
- **Plain MIDI, after the SysEx:** Bank Select, Program Change, and several CCs, all on
  channel 1. We verified these against the `.tem` files:
  - For "A5", Lié sent Bank Select 85/0, then Program 5, then CC3=40, CC9=10, CC16=0, CC18=0,
    CC81=65, CC47=116, CC83=10 and CC85=108. The file stores `BankSelectMsb="85"`,
    `ProgramChange="4"`, and macros 8 to 15 with `parameterId` 3, 9, 16, 18, 81, 47, 83, 85,
    whose `lastMappedValue` multiplied by 127 gives exactly those values.
  - For "B1", Lié sent Program 9, CC3=60, CC81=83 and CC107=78, which again match the file.
  - MIDI Monitor displays the program number starting at 1, while the files store it
    starting at 0, which is why `4` in the file appears as `5` on the wire display.

### What a hardware preset file contains (decoded from `/Library/Audio/Presets/ExpressiveE/Lie`)

- A `.tem` file is XML. The device-specific part is the `<STATE>` blob of the "External
  Device" filter, which is JUCE's base64 `MemoryBlock` format (`<size>.<characters>`, six bits
  per character, least significant bits first, alphabet `.A-Za-z0-9+`). Decoded, it starts
  with the header `VC2!` and a length, followed by a second XML document.
- That document has a `PROGRAMCHANGE` element (bank MSB, bank LSB and program, `-1` meaning
  not sent), a `PARAMETERS` list naming each of the 128 CCs as the synth labels them, and a
  `MIDICHANNEL` element.
- Across the 229 presets that have this block, there is no SysEx and no NRPN: the only message
  types are CC, Program Change and Bank Select, and every preset uses channel 1.
- Macros 0 to 15 are live mappings: each ties one sensor (0 to 3) to one CC (`parameterId`),
  over its own range (`min` to `max`, from 0 to 1 of the CC's travel) and through a named curve.
  `lastMappedValue` is only the value sent when the preset loads. An earlier version of this
  document called them "stored CCs with remembered values", which was wrong.
- Macros 16 to 19 are the four raw axes, bound to sensors 0, 1, 3 and 2 (so the Touché's
  CC16, CC17, CC18 and CC19 are sensors 0, 1, 3 and 2). Their `parameterId` is 0 or 1 in every
  preset we saw, so they carry no per-preset mapping.
- Sensor 4 is almost never used, and sensor 5 means "no sensor".
- The preset's graph is Midi Input, then External Device, then Midi Output. We therefore
  suspect that the translation from the Touché's fixed CC16 to CC19 into the synth's own CC
  numbers happens inside Lié and not inside the Touché, but we have not captured Lié's
  translated output to confirm this.

### What this means for the open questions below

- The first open question (the SysEx format for writing a mapping) is partly answered: loading
  a preset writes a SysEx configuration made of sensor curves and axis settings, which we can
  see but have not decoded in detail. We have not found any byte that carries a CC number, so
  we cannot yet change a mapping ourselves. Because the buttons already cover our use case,
  we decided not to pursue it further for now.
- A question that remains untested is whether the Touché forwards the Program Change and the
  CCs it receives on the Control Port to its own DIN MIDI output. If it does, a preset could
  change the patch of a synth without Lié. The test is to send a Program Change to the Control
  Port from our own tool and to watch the Touché's outputs.
- The third open question (whether CC80/81 can be keyed off) is answered: they can.
- Because the Bluetooth pedal already switches scenes, we do not use CC80 and CC81 for that.
  The next step is the bridge described in "Decision: where the Touché-to-VR-09 mapping
  lives". That bridge and `vr09.py` only work on Linux (ALSA raw MIDI), so the Touché has to
  be plugged into the machine that has the VR-09 attached.

### Decision: where the Touché-to-VR-09 mapping lives

Because the goal is to control VR-09 parameters from the Touché without Lié, we looked at the
three places where the translation from the Touché's controls to the VR-09's parameters could
live, and we decided that it has to live in software on the computer.

1. **In the Touché, written by Lié: not possible as far as we found.**
   - The SysEx that Lié sends carries sensor curves and axis settings, and we found no byte
     that carries a CC number. The mapping to a synth's CC numbers appears to happen inside
     Lié (the preset graph is Midi Input, External Device, Midi Output), so a hardware preset
     would be useless without Lié running.
   - This is a result of "we found no way", not a proof that the Touché cannot do it.
2. **In the VR-09: not possible.**
   - The VR-09 only reacts to a fixed list of CCs (volume, pan, expression, reverb and chorus
     sends, CC71 to CC77 for the synth, and the pedals). None of them has been tested yet as
     live incoming CC (see `cc-modulation-table.md`).
   - The Touché's axes send CC16 to CC19, which the VR-09 ignores. Most of the parameters we
     care about, such as the organ drawbars, effect levels and tones, can only be reached
     with DT1 SysEx and have no CC at all.
3. **In a bridge script on the computer: this is the design we chose.**
   - A script reads the Touché's axes (CC16 to CC19 on channel 1) and writes to the VR-09,
     using DT1 for the parameters that have no CC. DT1 is verified for reverb level, drawbars,
     effect levels and tones.
   - The map lives in a file in this repo, for example axis, then VR-09 address, range and an
     optional curve. It can be edited at any time without touching the Touché, and it needs
     no Lié or SysEx knowledge.
   - The map has to live in per-scene presets. A scene (a saved VR-09 sound) decides which
     parameters the four axes control, so that each scene can use the axes differently.
   - Because `vr09.py` opens the VR-09's MIDI port exclusively on Linux, the pedal script and
     the Touché bridge must run in one process, otherwise the second one cannot open the port.
   - Because an axis sends hundreds of values per second while it moves, the bridge must thin
     them out, for example one DT1 per axis every 10 to 20 ms. The recall tests already show
     that DT1 messages spaced 2 ms apart work.

Consequence: for a Linux box to run the live setup without Lié, we need to create scene
presets that forward the Touché's CCs to the corresponding VR-09 parameters. This needs
experimentation to find which controls make the most sense on the axes, and whether any CC
that the VR-09 documents (for example CC74 cutoff) works as a live incoming control.

The Bluetooth pedal remains the scene switcher, through `pedal_scenes.py`; the Touché's
selector buttons (CC80 and CC81) are not needed for that.

### What the presets map most often (survey of Lié's presets)

`tools/index_hardware_presets.py` writes `library/hardware_presets.json` (226 hardware presets
from 85 synths, of which 146 from 13 synths have mappings), and `tools/analyze_mappings.py`
counts the kinds of control. Because the presets of one synth mostly share one layout, the
meaningful unit is the 13 layouts, not the 146 presets.

- Filter cutoff and the oscillator and noise levels are mapped by 12 of the 13 synths. Cutoff
  sits on sensor 1 in nearly every layout.
- Sensor 0 carries levels and envelope (sustain, filter envelope amount), sensor 3 carries the
  mod wheel or LFO depth over its full travel, and sensor 2 carries effects, drive and
  resonance.
- A typical layout has 8 mappings spread over the 4 sensors, so each axis drives about two
  parameters at once, each over its own sub-range (median travel of 55 to 70 out of 127 on
  sensors 0 and 1, the full 127 on sensor 3).
- The patch type cannot be recovered from this data. The hardware presets have no tags and
  their names are bank slots such as `B2P3`. Only the 272 Factory presets are tagged (BASS,
  PAD, KEYS, LEAD and others, with 8 ORGAN), and they map unnamed plugin macros, so the two
  sets cannot be joined. `tools/survey_factory_presets.py` shows that their mappings are
  almost all linear and full range, with 2 or 4 targets per preset, mostly on sensors 0 and 1.
- Of the Roland presets, 14 of 15 synths have only a bare template. Only the System-8 has real
  patch presets (22). The Roland CC names follow the same convention as the VR-09's documented
  CCs (CC71 to CC77), which is why the Integra-7 template is the closest vocabulary match.

### Remap templates for the VR-09 (generated, untested)

`tools/make_templates.py` writes `web/public/maps/`: `targets.json` (66 VR-09 targets),
`templates/*.json` (36 templates) and `index.json`.

- A target is a DT1 write (address from Roland's implementation document) or a CC. Its status
  is `verified` (written alone on the unit: the nine upper drawbars), `recalled` (changed when
  a dump was recalled, never written alone: overdrive, leakage, key clicks, rotary switch) or
  `documented` (only in the document: lower drawbars, rotary speeds, EQ, per-part cutoff,
  resonance, envelope times and volume, and the CC sends).
- A template gives each axis (CC16 body, CC17 tone, CC18 modulation, CC19 effects) a list of
  targets, each with a range (which may descend to invert), a window of the axis travel, and a
  curve. The roles follow the layouts found in the survey.
- The 36 templates cover organ (12), synth lead, pad, bass, brass, strings, keys and pluck
  (14), piano and electric piano (4), crossfades between parts (4) and performance (2).
- They are proposals that we designed: the survey could not give a per-patch-type answer.
- Update, 2026-10-11: `tools/check_targets.py` tested the 53 parameter addresses on the unit. 45 accept
  writes, which became `verified`; 8 refuse them (see `midi-capabilities.md`) and became `unavailable`.
  Only the 13 CC targets are still `documented`, because a CC cannot be read back and has to be judged by
  ear. Of the 36 templates, 3 are fully verified, 9 have every address verified and CCs left to listen to,
  4 are partly working, and 20 have an axis with no working target (mostly the synth cutoff on CC17), so
  they need rework. The generator reports this in `index.json`, and the bridge page marks those templates
  and skips writes to unavailable targets.

### The bridge page (written, not yet run on the unit)

`web/public/touche-bridge.html` is served by the Astro dev server at
`http://localhost:8765/touche-bridge.html`. Web MIDI needs a secure context, which `localhost`
is; for an Android phone, run `adb reverse tcp:8765 tcp:8765` first.

- It connects to the Touché's Main Port and the VR-09 with SysEx permission, and shows live
  meters for CC16 to CC19 and the CC80 and CC81 buttons.
- It has two read-only VR-09 probes (Identity Request, RQ1 of the upper drawbars).
- The **CC out test** panel sends one CC (channel and CC chosen from the documented list) and,
  with "Send and compare", reads eight VR-09 blocks by RQ1 before and after and lists every
  address that changed. This is how the 135 documented-only target uses can be promoted to
  verified. It has been checked only against a simulated VR-09.
- The preset editor loads the templates, lets an axis drive several targets, and saves presets
  in the browser or as JSON. The bridge sends a message only when a quantised value changes, at
  most one every 5 ms.
- It has not been run in a browser against the real Touché and VR-09. The VR-09 appeared
  nowhere in this Mac's MIDI ports; it is on the Linux machine, where `vr09.py` must not hold
  the port while the page runs.

### Tools used

- `tools/index_hardware_presets.py`, `tools/analyze_mappings.py`, `tools/survey_factory_presets.py`
  and `tools/make_templates.py` are described in the sections above.

- `tools/midisniff.swift` is a small passive CoreMIDI listener that prints every message from
  the sources whose name contains the given text. Build it with `swiftc -O midisniff.swift`.
  We wrote it because ReceiveMIDI could not be installed through Homebrew on this Mac, where
  only the Command Line Tools are present and ReceiveMIDI needs a full Xcode.
- It cannot see what an application sends *to* the Touché. For that we used MIDI Monitor
  (Snoize) with its spy driver, which needed the `com.apple.quarantine` flag removed from
  `~/Library/Audio/MIDI Drivers/MIDI Monitor.plugin` and a restart of `MIDIServer` before it
  loaded.

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
