#!/usr/bin/env python3
"""Index Lié's hardware presets by the controls they move, so that we can pick the presets to base
the Touché-to-VR-09 maps on without listening to anything.

  index_hardware_presets.py [PRESET_DIR] [-o OUTPUT.json]

PRESET_DIR defaults to the macOS install folder of Lié. Each .tem file is XML, and the part that is
specific to the synth sits in the STATE blob of its "External Device" filter, in JUCE's base64
MemoryBlock format, which holds a second XML document (see docs/touche-lie-sniffing.md).

The output has one entry per preset: the synth, the Program Change it sends, the CC of each of the
four axes (macros 16 to 19) and its mappings (macros 0 to 15 with a parameter). A mapping is live: the
sensor drives the CC between low and high (0 to 127), through a named curve, and the CC starts at
"value" when the preset loads.
"""
import collections
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

DEFAULT_DIR = "/Library/Audio/Presets/ExpressiveE/Lie/Presets/Hardware Presets"
ALPHABET = ".ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+"
AXIS_MACROS = {"16": 0, "17": 1, "18": 2, "19": 3}

# The CCs the VR-09 document lists for the keyboard part, see docs/cc-modulation-table.md.
# None of them has been tested as live incoming CC yet.
VR09_CCS = {5, 7, 10, 11, 64, 65, 66, 67, 71, 72, 73, 74, 75, 76, 77, 91, 93}


def decode_blob(text):
    """Decode JUCE's "<size>.<characters>" format: six bits per character, least significant first."""
    size_text, characters = text.strip().split(".", 1)
    value, bits, out = 0, 0, bytearray()
    for character in characters:
        value |= ALPHABET.index(character) << bits
        bits += 6
        while bits >= 8:
            out.append(value & 0xFF)
            value >>= 8
            bits -= 8
    return bytes(out[:int(size_text)])


def external_device_xml(tree):
    """Return the decoded second XML document of the External Device filter, or None."""
    for filt in tree.iter("FILTER"):
        plugin = filt.find("PLUGIN")
        state = filt.find("STATE")
        if plugin is not None and state is not None and plugin.get("name") == "External Device":
            data = decode_blob(state.text)
            return data[data.index(b"<PLUGIN>"):].decode("latin1")
    return None


def parameter_names(body):
    return {int(n): label.strip() for n, label in re.findall(r'Parameter(\d+)="([^"]*)"', body)}


def program_change(body):
    match = re.search(r'BankSelectMsb="(-?\d+)" BankSelectLsb="(-?\d+)" ProgramChange="(-?\d+)"', body)
    if not match:
        return None
    msb, lsb, program = (int(g) for g in match.groups())
    return {"bank_msb": msb, "bank_lsb": lsb, "program": program}


def describe(path, synth):
    tree = ET.parse(path)
    body = external_device_xml(tree)
    if body is None:
        return None
    names = parameter_names(body)
    channel = re.search(r'MidiChannelNumber="(\d+)"', body)
    axes = [None] * 4
    mappings = []
    for macro in tree.iter("MACRO"):
        macro_id, parameter = macro.get("macroId"), macro.get("parameterId")
        if macro_id is None or parameter is None or int(float(parameter)) < 0:
            continue
        cc = int(float(parameter))
        entry = {
            "cc": cc,
            "name": names.get(cc, f"CC {cc}"),
            "sensor": int(float(macro.get("sensorIndex", 5))),
            "low": round(float(macro.get("min", 0)) * 127),
            "high": round(float(macro.get("max", 1)) * 127),
            "curve": macro.get("presetNameToDisplay", "default"),
            "value": round(float(macro.get("lastMappedValue", 0)) * 127),
        }
        if macro_id in AXIS_MACROS:
            axes[AXIS_MACROS[macro_id]] = entry
        elif int(macro_id) < 16:
            mappings.append(entry)
    return {
        "synth": synth,
        "preset": os.path.splitext(os.path.basename(path))[0],
        "channel": int(channel.group(1)) if channel else None,
        "program_change": program_change(body),
        "axes": axes,
        "mappings": mappings,
    }


def collect(root):
    presets = []
    for folder, _, files in sorted(os.walk(root)):
        for name in sorted(files):
            if name.endswith(".tem"):
                entry = describe(os.path.join(folder, name), os.path.basename(folder))
                if entry:
                    presets.append(entry)
    return presets


def summarize(presets):
    knob_counts = collections.Counter()
    knob_names = {}
    for preset in presets:
        for knob in preset["mappings"]:
            knob_counts[knob["cc"]] += 1
            knob_names.setdefault(knob["cc"], collections.Counter())[knob["name"]] += 1
    print(f"{len(presets)} presets, {len({p['synth'] for p in presets})} synths")
    print("\nMost used mapped CCs (VR-09 documents the ones marked *):")
    for cc, count in knob_counts.most_common(20):
        label = knob_names[cc].most_common(1)[0][0]
        print(f"  {'*' if cc in VR09_CCS else ' '} CC{cc:<3} {count:4}  {label}")

    by_synth = collections.defaultdict(lambda: [0, 0])
    for preset in presets:
        used = {k["cc"] for k in preset["mappings"]}
        by_synth[preset["synth"]][0] += 1
        by_synth[preset["synth"]][1] += len(used & VR09_CCS)
    print("\nSynths whose presets use the most VR-09 documented CCs, per preset:")
    ranked = sorted(by_synth.items(), key=lambda item: -item[1][1] / item[1][0])
    for synth, (count, hits) in ranked[:15]:
        print(f"  {hits / count:4.1f}  {synth} ({count} presets)")


def main():
    args = sys.argv[1:]
    output = None
    if "-o" in args:
        output = args[args.index("-o") + 1]
        del args[args.index("-o"):args.index("-o") + 2]
    root = args[0] if args else DEFAULT_DIR
    presets = collect(root)
    summarize(presets)
    if output:
        with open(output, "w") as f:
            json.dump(presets, f, indent=1)
        print(f"\nwritten to {output}")


main()
