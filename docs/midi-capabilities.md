# What the VR-09 can be controlled with over MIDI

Findings from testing a VR-09 over USB in MIDI IN Mode 2, cross-checked with the MIDI
Implementation document (`docs/VR-09_VR-730_MIDI_Implementation.pdf`), including its
implementation chart.

## Switching scenes from dumps

Terms used in this project:

- Registration: the keyboard's own stored setup, selected with its panel buttons.
- Dump: a snapshot of the keyboard's parameter values, saved as `dumps/NAME.json`. It is taken
  with `vr09.py dump NAME` after recalling a Registration with the panel.
- Recall: writing a dump's values back to the keyboard, one parameter per message, with
  `vr09.py recall NAME`. It takes about 0.15 s (66 messages, 2 ms apart), and afterwards the
  keyboard sounds like the Registration the dump came from.

The keyboard's own Registrations cannot be selected, read or edited over MIDI. A recall only
copies parameter values, so the display keeps showing the title, number and button LEDs of the
Registration last selected on the panel.

What was ruled out:

- Program Change and Bank Select to the keyboard parts: the document says they are not
  received.
- Program Change, with and without Bank Select, on channel 16 (the control channel in
  Mode 2): tested, no parameter changed.
- The keyboard part's whole address space (groups `00` to `7F`): scanned, no address follows
  the selected Registration number. Only groups `00` to `02` hold data. The title, the number
  and the button LEDs therefore stay on the previous Registration after a recall.
- The synth section (model `00 00 71`): see below, nothing follows the Registration.
- Every other model ID of 1 to 4 bytes: only model `47` answers, see below; it holds no
  Registration number.
- The Roland app does not claim to recall Registrations, see below.

What is still open:

- Loading Registrations from a USB memory stick (offline only, not live).

## Implementing a scene switcher

Everything needed to rewrite `vr09.py recall` in another language.

### Prerequisites and transport

- The unit must be in MIDI IN Mode 2: model ID `62` only addresses the keyboard part in that
  mode. Check it with an Identity Request, `F0 7E 7F 06 01 F7`. In Mode 2 the reply is
  `F0 7E 10 06 02 41 62 00 00 06 00 01 00 00 F7` (on our VR-09); in Mode 1 the bytes after
  `41` are `42 00 ...` instead.
- USB is class compliant. On Linux, `amidi -l` lists the port as `hw:C,D,0`, and the raw
  device is `/dev/snd/midiC<C>D<D>`, opened read and write. Writing bytes to it sends them,
  reading returns whatever the unit sent. No driver or library is needed.
- The card number can change when the unit is restarted or replugged, so look the port up by
  name ("VR-09") each time.

### Message format

All numbers are hexadecimal. Addresses and sizes are written with 7 bits per byte.

| Message | Bytes |
|---|---|
| DT1, keyboard part | `F0 41 10 62 12 a1 a2 a3 d1 ... dn sum F7` |
| RQ1, keyboard part | `F0 41 10 62 11 a1 a2 a3 s1 s2 s3 sum F7` |
| DT1, synth section | `F0 41 10 00 00 71 12 a1 a2 a3 a4 d1 ... dn sum F7` |
| RQ1, synth section | `F0 41 10 00 00 71 11 a1 a2 a3 a4 s1 s2 s3 s4 sum F7` |

- `10` is the device ID, `41` is Roland, `12` is DT1 (write), `11` is RQ1 (read).
- Checksum: `sum = (128 - (a1 + ... + d_n) mod 128) mod 128`, taken over the address and the
  data (DT1) or the address and the size (RQ1).
- Example from the document: setting the upper synth tone to JP8 Brass is
  `F0 41 10 62 12 01 03 01 59 01 00 21 F7`.
- The reply to an RQ1 is a DT1 with the requested address and data.

### Blocks

These blocks together hold everything that changed between Registrations. The `01 xx 00` slots
marked "not in the map" were found by scanning and hold part data like the documented ones.

| Name | Model | Start address | Size |
|---|---|---|---|
| system | `62` | `00 00 00` | `69` |
| upper piano | `62` | `01 01 00` | `65` |
| upper synth dual 2 | `62` | `01 02 00` | `65` |
| upper synth | `62` | `01 03 00` | `65` |
| lower piano | `62` | `01 11 00` | `65` |
| lower synth | `62` | `01 13 00` | `65` |
| upper piano dual 2 | `62` | `01 31 00` | `65` |
| drum | `62` | `01 41 00` | `65` |
| part slots, not in the map | `62` | `01 00 00`, `01 10 00`, `01 12 00`, `01 20 00`, `01 21 00`, `01 22 00`, `01 30 00`, `01 51 00` | `65` each |
| organ upper | `62` | `02 00 00` | `3A` |
| organ lower | `62` | `02 01 00` | `3A` |
| organ pedal | `62` | `02 02 00` | `3A` |
| synth set part upper 2 | `00 00 71` | `18 00 21 00` | `09` |
| synth set part upper 1 | `00 00 71` | `18 00 22 00` | `09` |
| synth set part lower | `00 00 71` | `18 00 25 00` | `09` |

### Write grouping

A DT1 must start at a parameter's own address. Most parameters take one byte, so most messages
carry one data byte. Three groups must be written as one message:

| Where | Start | Bytes | Content |
|---|---|---|---|
| system block | `00 00 00` | 2 | reverb type, reverb level |
| every part block and part slot | offset `00 01` | 3 | tone number, bank MSB, bank LSB |
| every synth set part | offset `00 06` | 3 | bank MSB, bank LSB, program |

If any byte of a group changes, send the whole group.

### Recall algorithm

```
capture, once per Registration
  the user recalls the Registration on the panel
  for each block
    send RQ1 for the whole block
    if no reply: wait 0.5 s and retry (the unit is silent for a moment after a recall)
  save address -> value for every byte

build the switch set, whenever the saved Registrations change
  varying = the addresses whose value is not the same in all saved Registrations

recall target
  for each write group touching an address in varying
    send DT1 with the target's values
    wait 2 ms
```

- No read is needed at recall time: writing the target's value at every varying address gives
  the same result whatever was loaded before.
- Gap: 0 ms overflows the unit's buffer ("Midi buffer full") and most writes are lost. 1, 2, 3,
  4, 5, 10 and 20 ms all worked. With our four Registrations the switch set was 66 messages, so
  a recall took 0.15 s at 2 ms.
- Limitation: an address that is the same in every saved Registration is never written. If it
  was changed by hand on the panel, a recall does not undo it. Writing every address of every
  block instead takes about 1,800 messages (1,821 bytes in all blocks), about 4 s at 2 ms.

### Reading replies

- Drop every byte from `F8` to `FF` before parsing: the unit sends MIDI clock, and realtime
  bytes may arrive in the middle of a SysEx reply.
- Keep only DT1 messages with the expected model ID, check their checksum, and keep only
  addresses inside the requested range: the unit also sends a DT1 by itself whenever a panel
  control changes.

### Known quirks

- After a recall, the bank LSB of synth set part upper 1 in Registration 3 reads back as 0
  instead of 64, and the octave shift (offset `00 07`) of the upper synth parts in
  Registration 4 reads back as 52 instead of 64. The sound was correct.
- The title, the number and the button LEDs of the selected Registration cannot be changed, so
  the display keeps showing the Registration that was last selected on the panel.
- A long burst of reads to undefined addresses once made the unit stop answering until it was
  restarted. Normal block reads never caused this.

### Dump files

`vr09.py` stores a dump as a JSON object. Each key is `block:XXXXXXXX`: the block name and the
address as one number, `a1 << 14 | a2 << 7 | a3` (keyboard part) or
`a1 << 21 | a2 << 14 | a3 << 7 | a4` (synth section), in 8 hexadecimal digits. Each value is the
byte stored there.

## Undocumented areas

Found with `scan.py` (reads only). Writing to them has not been tried.

### Synth section, model `00 00 71` (four-byte addresses)

Unlike the keyboard part, the synth section stays silent for some addresses, including the
Synth Tone areas the map documents (`19 21`, `19 41`, `1A 21`). The first address byte groups
that answer:

| Group | Content |
|---|---|
| `01 00 00 00` | 55 bytes of settings. Only `01 00 00 30` changed between Registrations (1 for Registrations 1 and 2, 0 for 3 and 4), so it is a flag, not a number. |
| `02 00 00 00` | 43 bytes of settings, unchanged between Registrations. |
| `10` to `17` | 256 stored entries, 32 per group, 4 address steps each: a 64-byte block starting with the name "InitPrf", a 16-byte block and a 64-byte block. All 256 are identical and at their initial values, so this memory is unused. |
| `18 00 00 00` | The live Synth Set, also named "InitPrf". Its parts are at `18 00 21 00`, `18 00 22 00` and `18 00 25 00` (documented). |
| `20 00` to `20 07` | 8 entries named "INIT STUDIO", all identical. |

### Model `47` (four-byte addresses)

- Answers only when the low digit of the first address byte is 0 to 9 (`00` to `09`, `10` to
  `19`, and so on). Every value is 0 to 15, half a byte.
- Data sits in groups `02` to `05`, `08` and `09`. Groups `08` and `09` change when a
  Registration is recalled, but they also change without any button press (561 values between
  two snapshots of the same Registration). Combined in pairs, the values form 4-byte words such
  as `ff ff ff e1` and no text.
- No value steps evenly across Registrations 1 to 4. The values that are stable repeat the same
  patterns at many addresses, which fits copies of sound-engine coefficients.
- Conclusion: the sound engine's working memory. Writing to it would not select a Registration
  and could put the engine in an odd state.

### Other observations

- The unit sends MIDI clock (`F8`), see Clock; `vr09.py` and `scan.py` ignore realtime bytes
  when parsing replies.
- Scanning at full speed once made the unit stop answering until it was restarted. With 20 ms
  between reads and an identity check every 32 reads, the scans above ran without problems.

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

## Documented addresses that this unit refuses

Checked on 2026-10-11 with `tools/check_targets.py`, which writes a value at each of the 53 parameter
addresses of the Touché remap catalog, reads it back, and puts the original value back (every original was
back at the end). 45 accept the write. These 8 do not: they read 0 in all 71 library dumps, whatever the patch,
and the write leaves the value at 0.

| Address | Parameter in Roland's map |
|---|---|
| `00 00 40`, `00 00 41` | organ EQ high and low (range 52 to 76) |
| `00 00 67` | overdrive dry mix level |
| `00 00 68` | rotary brake |
| `01 03 3A`, `01 13 3A` | upper and lower synth cutoff |
| `01 03 64`, `01 13 64` | upper and lower synth portamento time |

- The document covers the VR-09 and the VR-730, so these may exist only on the VR-730, or not be implemented
  at all; the unit does not say.
- The neighbouring synth parameters (resonance, attack, decay, release) do take writes, so this is not a
  property of the part block. Whether those accepted writes are also audible has not been checked by ear.
- The synth filter cutoff is therefore not reachable through DT1. CC74 on the part's channel reaches it, see
  "CC controls on the keyboard part, heard".
- Results are in `library/target-tests.json`; `tools/make_templates.py` folds them into the statuses of
  `web/public/maps/targets.json`.

## CC controls on the keyboard part, heard

A CC changes no stored parameter and cannot be read back, so each one was judged by ear with `tools/test_ccs.py`
(2026-10-12): it sets up a sound, plays a chord, moves the CC from its lowest to its highest value and back, and
asks. Probing CC71 to CC75 on channel 4 while reading `01 03 59` to `01 03 5C` showed the stored bytes unchanged.
The answers are in `library/target-tests.json`.

| Part (channel) | Heard working | Heard to do nothing |
|---|---|---|
| Upper (4) | CC11 expression, CC74 cutoff, CC71 resonance, CC73 attack, CC72 release, CC75 decay, CC77 vibrato depth, CC76 vibrato rate, CC1 modulation, CC93 chorus send | CC91 reverb send, CC10 pan |
| Lower (3) | CC74 cutoff, CC11 expression, CC91 reverb send, CC93 chorus send | none; CC71 to CC73, CC75 to CC77 and CC1 are untested |
| Second piano layer (1) | CC11 expression, CC93 chorus send | CC91 reverb send |
| Control (16) | CC11 overall volume | none |

- Roland's document is not a reliable guide here. Its chart lists CC71 to CC77 as "received in GM2 mode" and
  CC10, CC11, CC91 and CC93 as "not received in the keyboard part"; only CC71 to CC73 carry the tag for the keyboard
  part in the message descriptions. The unit nevertheless obeys CC74 to CC77 and CC93 on the keyboard part, and
  CC11 on channel 4 as well as on channel 16.
- The reverb verdicts may depend on the sound: reverb was on in the three test patches (types 2 and 5, levels 16 to
  25), the lower part answered, the upper part and the second piano layer did not. The upper reverb was heard on
  Super Saw Ld only.
- Envelope controls (attack, decay, release) and the reverb send only show at the start and end of notes, so the
  test plays repeated or stepped chords. The chorus send was judged on a plain saw (Saw Lead 1), because a supersaw
  already beats like a chorus, and the decay on a plucked string (Steel-str.Gt).
- Whether the address versions of resonance, attack, decay and release (`01 03 59` to `01 03 5C`, accepted and
  read back) and their CC versions act on the same value or stack has not been tried by ear.
- Expression (CC11) is documented as a volume of the part that is independent of the part volume (`01 03 04`);
  whether it leaves that stored byte alone was not probed. A CC keeps its value until another one arrives, so a
  mapping that leaves expression low keeps the keyboard almost mute; the bridge page resets the controllers
  before every load.

## Write rules for DT1

- One message writes one parameter. Gaps of 1 to 20 ms between messages all worked; no gap
  overflows the unit's buffer ("Midi buffer full") and most writes are lost.
- Addresses marked `#` in the map cannot start a message. The reverb level is written with the
  reverb type (`00 00 00`, two bytes), and the bank bytes with the tone number (offset `00 01`
  of a part, three bytes). The same holds for the Synth Set parts (offset `00 06`, three bytes).
- Writing a whole block as one message does not work: only some of its parameters are applied.
- Reads (RQ1) accept whole blocks.

## Clock

- The unit sends a steady MIDI clock (`F8`) even when no sequence is audible. On 2026-10-07
  it sent 380 ticks in 5 seconds (one every 13.2 ms), which is 189 BPM at 24 ticks per beat.
  The implementation chart says the clock is sent when the Composer plays, so the Composer or
  the rhythm may have been running without being audible.
- The VR-09 can therefore act as a clock source for a DAW or other gear. Not yet tested:
  whether 189 BPM is the tempo setting, and whether the clock follows a tempo change.
- The other direction is closed: the chart marks clock and start/stop as not recognised, and
  the address map has no tempo parameter, so the unit cannot follow an external tempo.
- No Active Sensing (`FE`) was seen during the measurement, although the document says it is
  sent every 250 ms.

## Drums with a sequencer

Tested on 2026-10-07 over USB in Mode 2: one kick drum (note 36), then two bars of a basic beat
at 100 BPM (closed hi-hat 42 on every eighth note, kick 36 on beats 1 and 3, snare 38 on beats
2 and 4, velocities 60 to 90), all on MIDI channel 11, while a chord was held on the keyboard.
Both the drums and the chord were heard. Not tested: dense playing on both at once (the number
of simultaneous voices is unknown), choosing the kit, and the drum level.

- The keyboard follows no external clock, so the sequencer sets the tempo.
- Leave the unit's own rhythm and the Composer off, or they play on top of the sequencer.
- The unit's USB output also sends what the player plays. Route only channel 11 from the
  sequencer back to the unit; echoing channels 3 and 4 would sound every note twice.
- The block at `01 41 00` is documented as the DRUM part, but its values do not match the map
  (offsets `02` to `04` hold values like organ drawbar levels), so its offsets for the kit and
  the level are unconfirmed.

## Choosing a tone

Piano, synth and drum tones are chosen by writing three bytes at offset `00 01` of the part,
in one message: tone number, bank MSB, bank LSB. The complete list is in `docs/tone-list.md`
(285 tones: 69 piano, 199 synth, 17 drum kits), and in `docs/tones.json` for programs. Both are
generated from pages 15 to 18 of Roland's document by `extract_tones.py`.

| Part | Block | Tone list used |
|---|---|---|
| Upper piano | `01 01 00` | Piano section |
| Upper piano dual 2 | `01 31 00` | Piano section |
| Lower piano | `01 11 00` | Piano section |
| Upper synth | `01 03 00` | Synthesizer section |
| Upper synth dual 2 | `01 02 00` | Synthesizer section |
| Lower synth | `01 13 00` | Synthesizer section |

Example: Grand Piano on the upper piano part is `F0 41 10 62 12 01 01 01 38 02 00 43 F7`: the
sum of address and data is 1 + 1 + 1 + 56 + 2 + 0 = 61, and 128 - 61 = 67 = `43`.

- The tone number is the value in parentheses in Roland's list (the Program Change number
  minus one). The document's own example agrees: JP8 Brass is listed as 90 (59h) and written
  as `59 01 00`.
- Checked against the unit: all 24 piano and synth tones stored in our four Registration dumps
  map to a name in the list, for example GrandPianoV, FM EP 1, FS Brass, JP8 Strings1, JP8
  Brass, Sine Lead 1 and Syn Bass.
- The piano section's OTHERS group holds the organ-like tones (Hard Organ, Mad Organ, Pipe
  Organ 1 to 3, Gospel Or.1 to 3), harpsichords, accordions, a harmonica and similar. The
  synth section's OTHERS group holds mallets, guitars and woodwinds.
- Tones marked (v1.03) in the list need System Program version 1.03 or newer.
- The organ has no tone list: its sound comes from the organ type (`00 00 42`), the drawbar
  levels, percussion, vibrato and rotary settings.
- Drum kits: the list gives a tone number and bank for each kit (for example Pop Kit is `03 01
  00`, TR-808 is `17 00 00`), but the block at `01 41 00` is not a tone triple: its values in our
  dumps (`51 08 08`, `51 06 06`) match no entry. Where the kit is selected is therefore unknown.
  Sounding a kit through channel 11 is not tested either.
- Not tested: writing a tone chosen from the list. Writing the tone bytes saved in a dump does
  work, which is how a recall of a dump works.

## Capabilities

The Status column says whether we verified it on the unit or only the document states it.
"Verified by recalling dumps" means that recalling dumps changed the sound as expected; the
parameter was not tested alone.

| What | Status | How |
|---|---|---|
| Recall a dump (the sound of a saved Registration) | Verified | `vr09.py recall NAME`, about 0.15 s, 66 DT1 messages 2 ms apart |
| Read any parameter of the current state | Verified | RQ1, whole blocks at once (`vr09.py dump`) |
| Change single parameters live | Verified | DT1, one parameter per message (reverb, drawbars, tones, effects) |
| Organ drawbars | Verified | `02 00 03` to `02 00 0B` (upper organ). The panel LEDs follow and the sound changes. |
| Reverb type and level | Verified | `00 00 00` (type) and `00 00 01` (level), written together |
| Select a section (piano, synth, organ) | Verified by recalling dumps | the MUTE flag of each part (offset `00 00`) |
| Choose the tone of a part | Verified by recalling dumps; list documented | tone number and the two bank bytes at offset `00 01`, written together; all tones in `docs/tone-list.md` |
| MFX type and level, delay type and level, overdrive, rotary, percussion, key click | Verified by recalling dumps | System block `00 00 xx` |
| Synth part tone (bank and program) | Verified by recalling dumps | `18 00 21/22/25 06` to `08` (synth section), written together |
| Watch panel changes live | Verified | the unit sends a DT1 by itself (`vr09.py watch`) |
| Use the unit as clock source | Observed, see Clock | it sends MIDI clock (`F8`) |
| Identify the unit and its MIDI mode | Verified | Identity Request; the reply differs between Mode 1 and Mode 2 |
| Play the parts from a sequencer | Documented | Mode 2 channels, see Channels in Mode 2 |
| Play drums from your own sequencer and clock | Verified | notes on channel 11 (`9A` note on, `8A` note off) sound while a chord is held on the keyboard, see Drums with a sequencer; the kit and its level were not tested |
| Rhythm and song volume | Documented address | `00 00 25` (rhythm level), `00 00 23` (song level) |
| Compressor and tone level | Documented address | `00 00 62` (compressor level), `00 00 61` (tone level) |
| Overall volume | Verified by ear | CC11 on channel 16, like the expression pedal |
| Per-part volume | Verified by address, expression by ear | DT1 `01 03 04` (upper synth) and its neighbours; CC11 on channels 4, 3 and 1 |
| Pan | Heard to do nothing on the upper part | CC10 on channel 4; not tried elsewhere |
| Reverb send per part | Verified by ear on the lower part only | CC91 does nothing on the upper part and the second piano layer |
| Chorus send per part | Verified by ear | CC93 on the upper part, the lower part and the second piano layer |
| Synth sound shaping | Verified by ear on the upper part | CC71 to CC77 and CC1; on the lower part only CC74 so far; the cutoff address is refused |
| Sustain, sostenuto, soft pedal, pitch bend | Documented | CC64, CC66, CC67, pitch bend |
| What each footswitch does | Documented address | `00 00 4F` and `00 00 50` |
| GM2 sounds on the other channels | Documented | Program Change and Bank Select work there, on channels 5 to 10, 12, 14 and 15 |

## What cannot be done

| What | Why |
|---|---|
| Select a Registration, or update its title, number or LEDs | No message or address for it: Program Change, every address space and every model ID were tested |
| Set the tempo | No tempo parameter in the address map |
| Sync the unit to an external clock | The chart marks clock as not recognised |
| Start or stop the rhythm or the Composer | Start/stop are not recognised; only a physical footswitch can do it, and the footswitch cannot be pressed over MIDI |

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
