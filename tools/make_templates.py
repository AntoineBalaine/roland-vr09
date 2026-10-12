#!/usr/bin/env python3
"""Generate the target catalog and the remap templates of the Touché-to-VR-09 bridge.

  make_templates.py [OUTPUT_DIR]        (default: web/public/maps)

Writes OUTPUT_DIR/targets.json, OUTPUT_DIR/templates/<name>.json and OUTPUT_DIR/index.json.

A target is one VR-09 parameter that a Touché axis can drive, either a DT1 write (address from the
implementation document) or a Control Change. Its status says how much we trust it:
  verified    written alone with DT1 on the unit (the upper organ drawbars)
  recalled    changes when a dump is recalled, never written alone
  documented  only listed in the implementation document

A template gives each of the four axes (CC16 to CC19) a list of targets. Every target has a range
(low and high, in the target's own units, low may be above high to invert), a window (the part of the
axis travel, 0 to 127, over which the range is swept) and a curve. The four axes follow the layouts of
the 13 hardware synths in Lié (see docs/touche-lie-sniffing.md): CC16 is the body of the sound
(level, envelope), CC17 the tone (cutoff, harmonics), CC18 the modulation and CC19 the effects.

Every template is a proposal: none has been tested on the unit yet.
"""
import json
import os
import sys

FOOTAGES = ["16'", "5 1/3'", "8'", "4'", "2 2/3'", "2'", "1 3/5'", "1 1/3'", "1'"]
DRAWBAR_IDS = ["16", "5f", "8", "4", "2f", "2", "1f", "1ff", "1"]  # Ids avoid slashes and quotes.


def dt1(target_id, label, address, low, high, status, note=""):
    return {"id": target_id, "label": label, "kind": "dt1", "address": address, "low": low, "high": high, "status": status, "note": note}


def cc(target_id, label, channel, number, status="documented", note=""):
    return {"id": target_id, "label": label, "kind": "cc", "channel": channel, "cc": number, "low": 0, "high": 127, "status": status, "note": note}


def build_targets():
    targets = []
    for manual, base, status in (("upper", 0x00, "verified"), ("lower", 0x01, "documented")):
        for i, footage in enumerate(FOOTAGES):
            targets.append(dt1(f"organ-{manual}-d{DRAWBAR_IDS[i]}", f"{manual.title()} organ drawbar {footage}", [0x02, base, 0x03 + i], 0, 8, status))

    system = [
        ("organ-level", "Organ level", 0x3C, 0, 127, "documented"),
        ("overdrive", "Organ overdrive", 0x3F, 0, 127, "recalled"),
        ("overdrive-dry", "Overdrive dry mix level", 0x67, 0, 127, "documented"),
        ("eq-high", "Organ EQ high (-12 to +12 dB)", 0x40, 52, 76, "documented"),
        ("eq-low", "Organ EQ low (-12 to +12 dB)", 0x41, 52, 76, "documented"),
        ("leakage", "Organ leakage level", 0x4A, 0, 127, "recalled"),
        ("click-on", "Key click on", 0x4B, 0, 63, "recalled"),
        ("click-off", "Key click off", 0x4C, 0, 63, "recalled"),
        ("rotary-fast", "Rotary fast / slow switch", 0x03, 0, 1, "recalled"),
        ("rotary-brake", "Rotary brake", 0x68, 0, 1, "documented"),
        ("woofer-slow", "Rotary woofer slow speed", 0x44, 0, 127, "documented"),
        ("woofer-fast", "Rotary woofer fast speed", 0x45, 0, 127, "documented"),
        ("woofer-accel", "Rotary woofer acceleration", 0x46, 0, 15, "documented"),
        ("tweeter-slow", "Rotary tweeter slow speed", 0x47, 0, 127, "documented"),
        ("tweeter-fast", "Rotary tweeter fast speed", 0x48, 0, 127, "documented"),
        ("tweeter-accel", "Rotary tweeter acceleration", 0x49, 0, 15, "documented"),
        ("rhythm-level", "Rhythm level", 0x25, 0, 127, "documented"),
        ("song-level", "Song level", 0x23, 0, 127, "documented"),
    ]
    for target_id, label, offset, low, high, status in system:
        targets.append(dt1(target_id, label, [0x00, 0x00, offset], low, high, status))

    # The part parameters share their offsets: 04 volume, 3A cutoff, 59 resonance, 5A attack, 5B decay, 5C release, 64 portamento time.
    parts = [("upper-synth", "Upper synth", 0x01, 0x03), ("lower-synth", "Lower synth", 0x01, 0x13)]
    for part_id, part_label, high_byte, low_byte in parts:
        for suffix, label, offset in (("cutoff", "cutoff", 0x3A), ("resonance", "resonance", 0x59), ("attack", "attack", 0x5A),
                                      ("decay", "decay", 0x5B), ("release", "release", 0x5C), ("portamento", "portamento time", 0x64)):
            targets.append(dt1(f"{part_id}-{suffix}", f"{part_label} {label}", [high_byte, low_byte, offset], 0, 127, "documented",
                               "Only meaningful when the part holds a synth tone." + (" The portamento switch must be on." if suffix == "portamento" else "")))
    volumes = [("upper-piano-volume", "Upper piano volume", 0x01, 0x01), ("upper-synth-volume", "Upper synth volume", 0x01, 0x03),
               ("upper-synth2-volume", "Upper synth (dual 2) volume", 0x01, 0x02), ("lower-piano-volume", "Lower piano volume", 0x01, 0x11),
               ("lower-synth-volume", "Lower synth volume", 0x01, 0x13)]
    for target_id, label, high_byte, low_byte in volumes:
        targets.append(dt1(target_id, label, [high_byte, low_byte, 0x04], 0, 127, "documented"))

    # Channels of MIDI IN Mode 2: 1 Piano Dual 2, 2 Pedal, 3 Lower, 4 Upper, 16 Control.
    targets += [
        cc("cc-upper-vibrato-depth", "Upper vibrato depth (CC77)", 4, 77), cc("cc-upper-vibrato-rate", "Upper vibrato rate (CC76)", 4, 76),
        cc("cc-upper-reverb", "Upper reverb send (CC91)", 4, 91), cc("cc-upper-chorus", "Upper chorus send (CC93)", 4, 93),
        cc("cc-upper-expression", "Upper expression (CC11)", 4, 11), cc("cc-upper-pan", "Upper pan (CC10)", 4, 10),
        cc("cc-lower-reverb", "Lower reverb send (CC91)", 3, 91), cc("cc-lower-chorus", "Lower chorus send (CC93)", 3, 93),
        cc("cc-lower-expression", "Lower expression (CC11)", 3, 11), cc("cc-piano-reverb", "Piano (dual 2) reverb send (CC91)", 1, 91),
        cc("cc-piano-chorus", "Piano (dual 2) chorus send (CC93)", 1, 93), cc("cc-piano-expression", "Piano (dual 2) expression (CC11)", 1, 11),
        cc("cc-master-expression", "Overall volume (CC11 on channel 16)", 16, 11),
    ]
    return targets


def t(target, low, high, window=(0, 127), curve="linear"):
    """One target of an axis. The range may descend (low above high) to invert the axis."""
    return {"target": target, "low": low, "high": high, "window": list(window), "curve": curve}


def template(name, patch_type, summary, body, tone, modulation, effects):
    return {
        "name": name, "patch_type": patch_type, "summary": summary, "status": "proposal, untested",
        "axes": [{"axis": 16, "role": "body", "targets": body}, {"axis": 17, "role": "tone", "targets": tone},
                 {"axis": 18, "role": "modulation", "targets": modulation}, {"axis": 19, "role": "effects", "targets": effects}],
    }


def drawbar_sweep(manual, indexes, start, step, width):
    """Raise several drawbars from 0 to 8 one after the other, each over its own window of the axis travel."""
    return [t(f"organ-{manual}-d{DRAWBAR_IDS[i]}", 0, 8, (start + n * step, start + n * step + width)) for n, i in enumerate(indexes)]


def build_templates():
    out = []
    # ---- organ ----
    out.append(template("organ-brightness-sweep", "organ", "Tone opens the upper harmonics one after the other; body is the level; modulation flips the rotary; effects add overdrive.",
        [t("organ-level", 70, 127)], drawbar_sweep("upper", [3, 4, 5, 6, 7, 8], 0, 15, 50),
        [t("rotary-fast", 0, 1)], [t("overdrive", 0, 90, curve="soft")]))
    out.append(template("organ-full-to-flute", "organ", "Tone crossfades from a full registration to a flute-like one.",
        [t("organ-level", 80, 127)],
        [t("organ-upper-d16", 8, 2), t("organ-upper-d8", 8, 4), t("organ-upper-d4", 2, 8), t("organ-upper-d2", 0, 6)],
        [t("leakage", 0, 60)], [t("click-on", 0, 40)]))
    out.append(template("organ-gospel-swell", "organ", "Body swells the low drawbars together; tone drives overdrive and brightness; effects add leakage.",
        [t("organ-upper-d16", 3, 8), t("organ-upper-d8", 4, 8), t("organ-upper-d4", 2, 6)],
        [t("overdrive", 10, 110, curve="soft"), t("eq-high", 60, 72)], [t("rotary-fast", 0, 1)], [t("leakage", 10, 90)]))
    out.append(template("organ-jazz-percussive", "organ", "A clean, percussive jazz sound: click and the 4' drawbar come in with the tone axis.",
        [t("click-on", 10, 63)], [t("organ-upper-d8", 6, 8), t("organ-upper-d4", 2, 8)], [t("rotary-fast", 0, 1)], [t("eq-high", 52, 70)]))
    out.append(template("organ-rock-grit", "organ", "Overdrive and the dry mix move in opposite directions so the grit grows without losing the attack.",
        [t("organ-level", 80, 127)], [t("overdrive", 20, 127, curve="soft"), t("overdrive-dry", 127, 40)],
        [t("eq-high", 52, 76), t("eq-low", 76, 56)], [t("rotary-fast", 0, 1), t("leakage", 20, 100)]))
    out.append(template("organ-rotary-morph", "organ", "All four axes shape the rotary speaker instead of the tone.",
        [t("woofer-slow", 30, 90), t("tweeter-slow", 30, 90)], [t("woofer-fast", 60, 127), t("tweeter-fast", 60, 127)],
        [t("woofer-accel", 0, 15), t("tweeter-accel", 0, 15)], [t("rotary-brake", 0, 1)]))
    out.append(template("organ-click-and-air", "organ", "Mechanical character of the organ: key clicks and leakage.",
        [t("click-on", 0, 63)], [t("click-off", 0, 63)], [t("leakage", 0, 127)], [t("eq-high", 52, 76)]))
    out.append(template("organ-eq-tilt", "organ", "Tone tilts the organ's EQ between dark and bright.",
        [t("organ-level", 60, 127)], [t("eq-high", 52, 76), t("eq-low", 76, 52)], [t("overdrive", 0, 70)], [t("leakage", 0, 80)]))
    out.append(template("organ-lower-swell", "organ", "Shapes the lower manual's drawbars; for a bass or comping part on the lower keyboard.",
        [t("organ-lower-d8", 0, 8), t("organ-lower-d16", 0, 6)], [t("organ-lower-d4", 0, 8), t("organ-lower-d2", 0, 6)],
        [t("organ-lower-d2f", 0, 8)], [t("organ-lower-d1", 0, 8)]))
    out.append(template("organ-pipe-registration", "organ", "A pipe-organ build-up: foundation fixed by the patch, mixtures come in over the tone axis.",
        [t("organ-level", 70, 127)], drawbar_sweep("upper", [3, 5, 7, 8], 10, 20, 60),
        [t("leakage", 0, 40)], [t("cc-upper-reverb", 20, 110)]))
    out.append(template("organ-ballad-warm", "organ", "A warm ballad sound: the tone axis darkens the EQ while the low drawbars rise.",
        [t("organ-upper-d16", 4, 8), t("organ-upper-d8", 6, 8)], [t("eq-high", 62, 52), t("overdrive", 0, 30)],
        [t("woofer-slow", 20, 70)], [t("cc-upper-reverb", 20, 100)]))
    out.append(template("organ-dynamic-volume", "organ", "The body axis is an organ volume pedal.",
        [t("organ-level", 30, 127)], [t("eq-high", 52, 76)], [t("rotary-fast", 0, 1)], [t("overdrive", 0, 60)]))

    # ---- synth ----
    out.append(template("synth-lead-expressive", "synth lead", "Cutoff and resonance open together; vibrato grows with the modulation axis.",
        [t("upper-synth-attack", 0, 40)], [t("upper-synth-cutoff", 30, 127), t("upper-synth-resonance", 10, 60)],
        [t("cc-upper-vibrato-depth", 0, 80), t("cc-upper-vibrato-rate", 40, 90)], [t("cc-upper-reverb", 20, 100), t("cc-upper-chorus", 0, 60)]))
    out.append(template("synth-lead-bite", "synth lead", "A biting lead: resonance on the body axis, cutoff on the tone axis.",
        [t("upper-synth-resonance", 0, 90)], [t("upper-synth-cutoff", 20, 127)], [t("upper-synth-portamento", 0, 70)], [t("upper-synth-decay", 40, 100)]))
    out.append(template("synth-lead-solo-glide", "synth lead", "For a mono lead with portamento on: glide time and vibrato are under the fingers.",
        [t("upper-synth-portamento", 0, 100)], [t("upper-synth-cutoff", 40, 127)], [t("cc-upper-vibrato-depth", 0, 100)], [t("cc-upper-reverb", 10, 90)]))
    out.append(template("synth-pad-evolve", "synth pad", "A slow pad: attack and cutoff evolve; the effects axis opens reverb and release.",
        [t("upper-synth-attack", 20, 110)], [t("upper-synth-cutoff", 20, 110)], [t("cc-upper-vibrato-depth", 0, 60)],
        [t("cc-upper-reverb", 30, 127), t("upper-synth-release", 40, 127)]))
    out.append(template("synth-pad-breath", "synth pad", "Breathing pad: envelope times on the body and effects axes, filter movement on the tone axis.",
        [t("upper-synth-attack", 10, 100)], [t("upper-synth-cutoff", 30, 100)], [t("upper-synth-resonance", 0, 50)], [t("upper-synth-release", 30, 127)]))
    out.append(template("synth-pad-ambient", "synth pad", "Wide and washed: effects dominate.",
        [t("upper-synth-volume", 60, 127)], [t("upper-synth-cutoff", 40, 110)], [t("cc-upper-chorus", 0, 100)], [t("cc-upper-reverb", 30, 127)]))
    out.append(template("synth-bass-punch", "synth bass", "A punchy bass: cutoff and resonance on tone, decay on body.",
        [t("upper-synth-decay", 20, 80)], [t("upper-synth-cutoff", 20, 100), t("upper-synth-resonance", 0, 50)],
        [t("upper-synth-portamento", 0, 60)], [t("upper-synth-volume", 80, 127)]))
    out.append(template("synth-bass-growl", "synth bass", "Resonance does the growling; attack is shortened as the tone opens.",
        [t("upper-synth-resonance", 10, 100)], [t("upper-synth-cutoff", 10, 90), t("upper-synth-attack", 40, 0)],
        [t("upper-synth-release", 10, 60)], [t("cc-upper-chorus", 0, 50)]))
    out.append(template("synth-brass-swell", "synth brass", "A brass swell: attack lengthens while the filter opens.",
        [t("upper-synth-attack", 0, 70)], [t("upper-synth-cutoff", 40, 120)], [t("cc-upper-vibrato-depth", 0, 60)], [t("cc-upper-reverb", 10, 80)]))
    out.append(template("synth-strings-ensemble", "synth strings", "String sections: slow attack, chorus on the effects axis, vibrato on the modulation axis.",
        [t("upper-synth-attack", 10, 90)], [t("upper-synth-cutoff", 40, 120)], [t("cc-upper-vibrato-depth", 0, 70)],
        [t("cc-upper-chorus", 0, 90), t("cc-upper-reverb", 20, 90)]))
    out.append(template("synth-keys-electric", "synth keys", "Electric-piano-like synth keys: decay on body, tremolo-ish vibrato, reverb.",
        [t("upper-synth-decay", 30, 100)], [t("upper-synth-cutoff", 50, 127)], [t("cc-upper-vibrato-depth", 0, 60), t("cc-upper-vibrato-rate", 50, 100)],
        [t("cc-upper-reverb", 10, 90)]))
    out.append(template("synth-pluck", "synth pluck", "Plucked sounds: decay and release are short and shaped together.",
        [t("upper-synth-decay", 10, 90), t("upper-synth-release", 10, 70)], [t("upper-synth-cutoff", 30, 127)], [t("upper-synth-resonance", 0, 70)],
        [t("cc-upper-reverb", 10, 80)]))
    out.append(template("synth-filter-only", "synth", "The simplest synth template: cutoff, resonance, reverb and vibrato, one each.",
        [t("upper-synth-resonance", 0, 80)], [t("upper-synth-cutoff", 10, 127)], [t("cc-upper-vibrato-depth", 0, 90)], [t("cc-upper-reverb", 0, 100)]))
    out.append(template("synth-lower-layer", "synth", "Same ideas as synth-filter-only, but on the lower synth part.",
        [t("lower-synth-resonance", 0, 80)], [t("lower-synth-cutoff", 10, 127)], [t("lower-synth-attack", 0, 70)], [t("cc-lower-reverb", 0, 100)]))

    # ---- piano ----
    out.append(template("piano-concert", "piano", "A concert piano: expression on body, reverb on effects, chorus kept subtle.",
        [t("cc-piano-expression", 60, 127)], [t("cc-piano-chorus", 0, 40)], [t("cc-upper-pan", 54, 74)], [t("cc-piano-reverb", 20, 110)]))
    out.append(template("piano-ambient", "piano", "A cinematic piano: reverb and chorus open together.",
        [t("cc-piano-expression", 70, 127)], [t("cc-piano-chorus", 0, 90)], [t("cc-upper-pan", 40, 88)], [t("cc-piano-reverb", 30, 127)]))
    out.append(template("piano-ep-chorus", "electric piano", "An electric piano with chorus on the tone axis.",
        [t("cc-piano-expression", 60, 127)], [t("cc-piano-chorus", 10, 100)], [t("cc-upper-vibrato-depth", 0, 50)], [t("cc-piano-reverb", 10, 80)]))
    out.append(template("piano-intimate", "piano", "A dry, close piano: almost no effects, just expression and a little width.",
        [t("cc-piano-expression", 70, 127)], [t("cc-piano-reverb", 0, 50)], [t("cc-upper-pan", 58, 70)], [t("cc-piano-chorus", 0, 20)]))

    # ---- crossfades between parts ----
    out.append(template("xfade-piano-synth", "layer", "Crossfade the upper piano into the upper synth.",
        [t("upper-piano-volume", 127, 0)], [t("upper-synth-volume", 0, 127)], [t("upper-synth-cutoff", 40, 120)], [t("cc-upper-reverb", 10, 90)]))
    out.append(template("xfade-upper-lower", "layer", "Crossfade between the upper and lower synth parts.",
        [t("upper-synth-volume", 127, 0)], [t("lower-synth-volume", 0, 127)], [t("upper-synth-cutoff", 40, 120)], [t("lower-synth-cutoff", 40, 120)]))
    out.append(template("xfade-organ-synth", "layer", "Crossfade the organ into the upper synth.",
        [t("organ-level", 127, 20)], [t("upper-synth-volume", 20, 127)], [t("rotary-fast", 0, 1)], [t("cc-upper-reverb", 10, 90)]))
    out.append(template("xfade-piano-organ", "layer", "Crossfade the upper piano into the organ.",
        [t("upper-piano-volume", 127, 20)], [t("organ-level", 20, 127)], [t("rotary-fast", 0, 1)], [t("cc-piano-reverb", 10, 90)]))

    # ---- performance ----
    out.append(template("perform-expression-reverb", "any", "A neutral performance template: overall volume, reverb and chorus sends.",
        [t("cc-master-expression", 50, 127)], [t("cc-upper-reverb", 0, 110)], [t("cc-upper-chorus", 0, 90)], [t("cc-upper-vibrato-depth", 0, 90)]))
    out.append(template("perform-width", "any", "Stereo width: pan and chorus on the sides, reverb at the back.",
        [t("cc-master-expression", 60, 127)], [t("cc-upper-pan", 20, 108)], [t("cc-upper-chorus", 0, 100)], [t("cc-upper-reverb", 10, 110)]))
    return out


def check(targets, templates):
    ids = {x["id"] for x in targets}
    assert len(ids) == len(targets), "duplicate target ids"
    names = set()
    for tpl in templates:
        assert tpl["name"] not in names, tpl["name"]
        names.add(tpl["name"])
        for axis in tpl["axes"]:
            assert axis["targets"], (tpl["name"], axis["axis"], "no targets")
            for item in axis["targets"]:
                assert item["target"] in ids, (tpl["name"], item["target"])
                low, high = (x for x in (item["low"], item["high"]))
                bounds = next(x for x in targets if x["id"] == item["target"])
                assert bounds["low"] <= min(low, high) and max(low, high) <= bounds["high"], (tpl["name"], item["target"], low, high)


def main():
    out_dir = sys.argv[1] if len(sys.argv) > 1 else "web/public/maps"
    targets, templates = build_targets(), build_templates()
    check(targets, templates)
    os.makedirs(os.path.join(out_dir, "templates"), exist_ok=True)
    with open(os.path.join(out_dir, "targets.json"), "w") as f:
        json.dump(targets, f, indent=1)
    index = []
    for tpl in templates:
        with open(os.path.join(out_dir, "templates", tpl["name"] + ".json"), "w") as f:
            json.dump(tpl, f, indent=1)
        index.append({"name": tpl["name"], "patch_type": tpl["patch_type"], "summary": tpl["summary"]})
    with open(os.path.join(out_dir, "index.json"), "w") as f:
        json.dump(index, f, indent=1)
    kinds = {}
    for tpl in templates:
        kinds[tpl["patch_type"]] = kinds.get(tpl["patch_type"], 0) + 1
    print(f"{len(targets)} targets, {len(templates)} templates written to {out_dir}")
    print(dict(sorted(kinds.items())))


main()
