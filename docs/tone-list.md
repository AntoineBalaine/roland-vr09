# VR-09 tone list

Extracted from pages 15 to 18 of `docs/VR-09_VR-730_MIDI_Implementation.pdf` with
`extract_tones.py`, which also writes `docs/tones.json`. To select a tone, write the three bytes
Tone number, Bank MSB, Bank LSB (in that order, in one message) at offset `00 01` of the part.
Values are in hexadecimal. The tone number is the Program Change number minus one, which is
the value in parentheses in Roland's list.

Tones marked (v1.03) were added in VR-09 System Program version 1.03: older firmware does not have them.

## Piano section

### Piano

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| GrandPianoV | `38` | `06` | `00` |
| Grand Piano | `38` | `02` | `00` |
| GrandPianoV2 | `38` | `07` | `00` |
| Rock Piano | `4F` | `01` | `00` |
| Mono Piano | `4F` | `03` | `00` |
| JUNO Piano2 | `38` | `0C` | `00` |
| JD Piano | `4F` | `02` | `00` |
| SA Piano | `4F` | `04` | `00` |
| Y2K Concerto2 | `38` | `0B` | `00` |
| Honky-tonk | `39` | `00` | `00` |
| Echo Piano | `38` | `0A` | `00` |
| European Pno | `38` | `09` | `00` |
| Classic Pno | `38` | `08` | `00` |

### E.Piano

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| 75 Tine EP2 | `07` | `01` | `00` |
| Vintage EP | `3A` | `06` | `00` |
| Stone EP | `3A` | `0D` | `00` |
| Pure EP Trem2 | `07` | `02` | `00` |
| Tremolo EP | `3A` | `0E` | `00` |
| Dyno E.Piano | `3A` | `03` | `00` |
| '60s E.Piano | `3A` | `05` | `00` |
| '60s TremEP | `3A` | `0C` | `00` |
| Stiky EP2 | `07` | `03` | `00` |
| Water EP2 | `07` | `04` | `00` |
| FM EP 1 | `3B` | `02` | `00` |
| FM EP 2 | `3B` | `03` | `00` |
| 80's EP | `3B` | `04` | `00` |
| Pure EP (v1.03) | `3B` | `05` | `00` |
| Phase EP (v1.03) | `3B` | `06` | `00` |
| Tremolo EP 2 (v1.03) | `3B` | `07` | `00` |
| VR EP 1 (v1.03) | `3B` | `08` | `00` |
| VR EP 2 (v1.03) | `3B` | `09` | `00` |
| Pure Wurly (v1.03) | `3B` | `0A` | `00` |
| SA EP (v1.03) | `3B` | `0B` | `00` |
| SA EP Stack (v1.03) | `3B` | `0C` | `00` |
| Metalic EP (v1.03) | `3B` | `0D` | `00` |
| Hybrid EP (v1.03) | `3B` | `0E` | `00` |

### CLAV

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Clav 1 | `50` | `03` | `00` |
| Clav 2 | `50` | `04` | `00` |
| Phase Clav 1 | `50` | `06` | `00` |
| T-Wah Clav | `50` | `09` | `00` |
| Comp Clav | `50` | `0A` | `00` |
| BrillClav DB | `50` | `01` | `00` |
| Pulse Clav | `50` | `08` | `00` |
| Phase Clav 2 | `50` | `07` | `00` |
| Clav 3 | `50` | `02` | `00` |
| Velo Clav | `50` | `05` | `00` |

### Others

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Harmonderca | `49` | `04` | `00` |
| BluesHarp | `49` | `05` | `00` |
| Accordion | `48` | `05` | `00` |
| Fr Musset | `48` | `01` | `00` |
| La Seine | `48` | `08` | `00` |
| Bandoneon | `55` | `00` | `00` |
| D50 Fantasia2 | `2D` | `0C` | `00` |
| Fantasia JV2 | `2D` | `0D` | `00` |
| XV Crystal2 | `2D` | `0E` | `00` |
| OrganBell | `2F` | `0E` | `00` |
| Fantasy | `2F` | `09` | `00` |
| HarpsiSingle | `42` | `01` | `00` |
| HarpsiDouble | `42` | `02` | `00` |
| Celesta | `51` | `00` | `00` |
| Harp | `43` | `00` | `00` |
| Hard Organ | `0C` | `00` | `00` |
| Mad Organ | `0D` | `00` | `00` |
| Pipe Organ1 | `14` | `00` | `00` |
| Pipe Organ2 | `15` | `00` | `00` |
| Pipe Organ3 | `19` | `00` | `00` |
| Gospel Or.1 | `1A` | `00` | `00` |
| Gospel Or.2 | `1B` | `00` | `00` |
| Gospel Or.3 | `1F` | `00` | `00` |

## Synthesizer section

### Brass

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| JP8 Brass | `59` | `01` | `00` |
| 80s Brs 1 | `59` | `04` | `00` |
| Hybrid Brass | `59` | `08` | `00` |
| JUNO Brs | `59` | `02` | `00` |
| Soft Syn Brs | `59` | `06` | `00` |
| ResoSweepBrs | `59` | `05` | `00` |
| Jmp Brass | `59` | `09` | `00` |
| 80s Brs 2 | `59` | `03` | `00` |
| Analog Brs | `59` | `07` | `00` |
| X Brs Sect2 | `41` | `07` | `00` |
| Sax Section2 | `41` | `08` | `00` |
| FS Brass | `41` | `05` | `00` |
| StackTp Sect | `40` | `0F` | `00` |
| Tp/TbSecStac | `41` | `06` | `00` |
| N.Trumpet | `5E` | `09` | `00` |
| Classical Tp | `5E` | `0A` | `00` |
| Mute Tp | `5F` | `05` | `00` |
| Harmon Mute | `5F` | `06` | `00` |
| Cup Mute Tp | `5F` | `02` | `00` |
| Solo Tb | `68` | `06` | `00` |
| Soft Tb | `68` | `05` | `00` |
| N.Alto Sax | `60` | `06` | `00` |
| Blow Sax | `60` | `02` | `00` |
| Soprano Sax | `69` | `00` | `00` |
| F.Horns Sect | `58` | `0A` | `00` |

### Strings

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| JP8 Strings1 | `2C` | `02` | `00` |
| JP8 Strings2 | `2C` | `03` | `00` |
| Syn Strings1 | `2C` | `0D` | `00` |
| Syn Strings2 | `2C` | `0E` | `00` |
| JUNO Str 1 | `2C` | `04` | `00` |
| JUNO Str 2 | `2C` | `05` | `00` |
| OB Strings | `2C` | `06` | `00` |
| Vintage | `2C` | `07` | `00` |
| Oct Str | `2C` | `08` | `00` |
| Brite Str | `2C` | `09` | `00` |
| Digi Str | `2C` | `0A` | `00` |
| Hybrid Str | `2C` | `0B` | `00` |
| Phase Str | `2C` | `0C` | `00` |
| Full Strings | `29` | `05` | `00` |
| Dyn Strings | `29` | `04` | `00` |
| Slow Strings | `2A` | `04` | `00` |
| Mood Strings | `2A` | `03` | `00` |
| Pizzicato | `37` | `00` | `00` |
| Violin | `5C` | `06` | `00` |
| Cello | `5D` | `00` | `00` |

### Synth Lead

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Saw Lead 1 | `6F` | `0B` | `00` |
| Super Saw Ld | `6F` | `0D` | `00` |
| Pure Sine Ld2 | `70` | `02` | `00` |
| Pure Lead | `6E` | `06` | `00` |
| Sine Lead 1 | `6E` | `0F` | `00` |
| Anadroid2 | `70` | `03` | `00` |
| Sky Bit | `6F` | `06` | `00` |
| Punker | `3F` | `0A` | `00` |
| Fat GR Lead | `6E` | `0E` | `00` |
| P5 Sync Lead2 | `70` | `04` | `00` |
| OSC-SyncLd 1 | `6F` | `03` | `00` |
| OSC-SyncLd 2 | `6F` | `02` | `00` |
| Saw Lead 2 | `6E` | `08` | `00` |
| Saw Lead 3 | `6F` | `0A` | `00` |
| Square Lead1 | `6E` | `0C` | `00` |
| Square Lead2 | `6E` | `0D` | `00` |
| Square Lead32 | `70` | `05` | `00` |
| Pulse Lead | `6E` | `0B` | `00` |
| Searing COSM2 | `3F` | `0B` | `00` |
| LP Dist | `3F` | `08` | `00` |
| FS Plugged | `3F` | `09` | `00` |
| Pure Square | `6F` | `0C` | `00` |
| Trance Key | `6D` | `0E` | `00` |
| Bit Poly 1 | `6F` | `09` | `00` |
| Bit Poly 2 | `6F` | `05` | `00` |
| Tekno Lead | `6F` | `04` | `00` |
| Saws Key | `6D` | `05` | `00` |
| Super Saws | `6E` | `0A` | `00` |
| Poly Slice | `6F` | `08` | `00` |
| Poly Syn 1 | `6D` | `06` | `00` |
| Poly Syn 2 | `6D` | `07` | `00` |
| Poly Syn 3 | `6D` | `08` | `00` |
| Wire String | `6D` | `09` | `00` |
| Cutter Key | `6D` | `0A` | `00` |
| Digi Key 1 | `6D` | `0B` | `00` |
| Digi Key 2 | `6D` | `0C` | `00` |
| J-Pop Kira | `6D` | `0D` | `00` |
| Sqr Key | `6D` | `0F` | `00` |
| JP80 SynHarp | `2F` | `0D` | `00` |
| Bell Key | `2F` | `0F` | `00` |
| AnalogBell 1 | `2F` | `0B` | `00` |
| AnalogBell 2 | `2F` | `0C` | `00` |
| Pipe Key | `34` | `0C` | `00` |
| Pluck Synth2 | `70` | `06` | `00` |
| SEQ 1 | `6E` | `07` | `00` |
| SEQ 2 | `6E` | `05` | `00` |
| Crossfire | `6E` | `09` | `00` |
| Bodyart | `6F` | `07` | `00` |
| SL JP8 5th (v1.03) | `01` | `01` | `00` |
| SL JP8 Key (v1.03) | `01` | `03` | `00` |
| SL JP6 Ld 1 (v1.03) | `01` | `05` | `00` |
| SL JP6 Ld 2 (v1.03) | `01` | `08` | `00` |
| SL Juno ODLd (v1.03) | `01` | `0B` | `00` |
| SL Juno Key (v1.03) | `01` | `0D` | `00` |
| SL D50 Pizz (v1.03) | `01` | `0E` | `00` |
| SL D50 SftLd (v1.03) | `01` | `0F` | `00` |

### BASS

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| ElectroBass2 | `7C` | `03` | `00` |
| Foundation2 | `7C` | `04` | `00` |
| Chow Bs2 | `7C` | `05` | `00` |
| Syn Bass | `7B` | `03` | `00` |
| MG Bass | `7B` | `02` | `00` |
| Fat Analog | `7B` | `0B` | `00` |
| Detune Bs 1 | `7B` | `05` | `00` |
| PWM Bass | `7C` | `02` | `00` |
| Unison Bs | `7B` | `07` | `00` |
| Monster Bs | `7B` | `0C` | `00` |
| Chorus Bass2 | `76` | `08` | `00` |
| Finger Bs | `76` | `05` | `00` |
| RichFretless | `76` | `07` | `00` |
| N.AcousticBs | `75` | `06` | `00` |
| Detune Bs 2 | `7B` | `0E` | `00` |
| Detune Bs 3 | `7B` | `0F` | `00` |
| Low Bass | `7B` | `0A` | `00` |
| FM Bass | `7B` | `04` | `00` |
| P5 Bass | `7B` | `06` | `00` |
| Camblast | `7B` | `08` | `00` |
| Reso Bs | `7B` | `09` | `00` |
| Carmelcorn | `7B` | `0D` | `00` |
| Fretless Bs | `76` | `06` | `00` |
| Picked Bs | `77` | `02` | `00` |
| Slap Bass | `77` | `03` | `00` |
| Chicken Bass | `77` | `04` | `00` |

### Synth Pad

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Soft Pad 1 | `2E` | `08` | `00` |
| Str Pad | `2D` | `0A` | `00` |
| Atk Pad | `2D` | `0B` | `00` |
| Heaven Pad | `2E` | `0A` | `00` |
| Sweep Pad | `2F` | `05` | `00` |
| Dreaming | `2F` | `0A` | `00` |
| Stone Pad | `2F` | `03` | `00` |
| Syn Pad 1 | `2E` | `0E` | `00` |
| JP8 Hollow | `2E` | `0B` | `00` |
| Soft Pad 2 | `2E` | `07` | `00` |
| Soft Pad 3 | `2E` | `06` | `00` |
| JP8 Stone | `2F` | `04` | `00` |
| Organ Pad | `2E` | `09` | `00` |
| Glass Pad | `2E` | `0C` | `00` |
| Slow Pad | `2E` | `0F` | `00` |
| Syn Pad 2 | `2E` | `0D` | `00` |
| Trance Pad | `2F` | `06` | `00` |
| 5th Pad | `2F` | `07` | `00` |
| LFO Hollow | `2F` | `08` | `00` |
| SL JP8 BrtPd (v1.03) | `01` | `02` | `00` |
| SL JP8 SftPd (v1.03) | `01` | `04` | `00` |
| SL JP6 LFOPd (v1.03) | `01` | `06` | `00` |
| SL Juno Sft (v1.03) | `01` | `09` | `00` |
| SL Juno LFO (v1.03) | `01` | `0A` | `00` |
| SL Juno Uni (v1.03) | `01` | `0C` | `00` |

### Choir

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Vox Pad 1 | `34` | `07` | `00` |
| HyperVentChr | `34` | `0B` | `00` |
| JD80 SoftVox | `34` | `06` | `00` |
| Vox Pad 2 | `34` | `08` | `00` |
| Vox Pad 3 | `34` | `0A` | `00` |
| Syn Vox 1 | `34` | `05` | `00` |
| Vox Pad 4 | `34` | `09` | `00` |
| VP-330 Chr | `32` | `03` | `00` |
| Jazz Scat | `31` | `01` | `00` |
| Jazz Doo | `31` | `02` | `00` |
| Classical | `30` | `02` | `00` |
| Gregorian | `30` | `01` | `00` |
| Choir | `30` | `00` | `00` |

### SFX

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| FX 1 | `57` | `08` | `00` |
| FX 2 | `57` | `09` | `00` |
| FX 3 | `57` | `03` | `00` |
| FX 4 | `57` | `07` | `00` |
| FX 5 | `57` | `0C` | `00` |
| FX 6 | `57` | `01` | `00` |
| FX 7 | `57` | `02` | `00` |
| FX 8 | `57` | `04` | `00` |
| FX 9 | `57` | `05` | `00` |
| FX 10 | `57` | `06` | `00` |
| FX 11 | `57` | `0A` | `00` |
| Sci-Fi Sweep | `57` | `0B` | `00` |
| Hover Dive | `57` | `0D` | `00` |
| Orch Hit | `7F` | `06` | `00` |
| Philly Hit | `7F` | `07` | `00` |
| House Hit | `7F` | `08` | `00` |
| SL JP6 Fx (v1.03) | `01` | `07` | `00` |

### Others

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Vibraphone | `44` | `00` | `00` |
| Marimba | `45` | `00` | `00` |
| Glockenspiel | `52` | `00` | `00` |
| Xylophone | `53` | `00` | `00` |
| Steel Drums | `5B` | `00` | `00` |
| JC E.Guitar | `3E` | `02` | `00` |
| Muted Guitar | `3F` | `04` | `00` |
| Steel Away2 | `3D` | `06` | `00` |
| Pastoral2 | `3D` | `07` | `00` |
| Steel-str.Gt | `3D` | `00` | `00` |
| Jazz Guitar | `3E` | `00` | `00` |
| Nylon-str.Gt | `3C` | `00` | `00` |
| Ac.Gtr Sld | `3D` | `03` | `00` |
| N.Flute | `62` | `08` | `00` |
| Andes Mood | `63` | `05` | `00` |
| Clarinet | `65` | `01` | `00` |
| Oboe | `64` | `00` | `00` |

## Drum section

| Name | Tone number | Bank MSB | Bank LSB |
|---|---|---|---|
| Pop Kit | `03` | `01` | `00` |
| Rock Kit | `11` | `01` | `00` |
| Jazz Brush | `2B` | `01` | `00` |
| TR-808 | `17` | `00` | `00` |
| CR-78 | `1B` | `00` | `00` |
| TR-606 | `1C` | `00` | `00` |
| TR-707 | `1D` | `00` | `00` |
| TR-909 | `1E` | `00` | `00` |
| Hip Hop | `09` | `00` | `00` |
| House | `0D` | `00` | `00` |
| Dance | `1A` | `00` | `00` |
| Vox Drum | `3F` | `01` | `00` |
| StandardKit2 | `00` | `01` | `00` |
| Room Kit | `08` | `00` | `00` |
| Power Kit | `10` | `00` | `00` |
| Jazz Kit | `20` | `00` | `00` |
| Sound Effect | `38` | `00` | `00` |
