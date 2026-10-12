#!/usr/bin/env python3
"""Count which kinds of control Lié's hardware presets map to the Touché, from library/hardware_presets.json.

  analyze_mappings.py [hardware_presets.json]

The JSON comes from index_hardware_presets.py. Each mapping names a parameter of a real synth (for
example "FILTER CUTOFF" or "Osc 2 Level"), so the names are sorted into functions with the rules below.
The presets carry no patch type: their names are bank slots such as B2P3, and none of them has a TAG.
Only the Factory presets are tagged (BASS, PAD, ...), and they map unnamed plugin macros, so the two
sets cannot be joined, and this script reports nothing per patch type.
"""
import collections
import json
import re
import statistics
import sys

# Order matters: the first rule that matches wins, so the narrow rules come before the wide ones.
RULES = [
    ("mod wheel (CC1)", r"mod ?wheel|modulation wheel|^cc 1$"),
    ("filter envelope amount", r"(\benv\b|\beg\b|envelope).*(amt|amount|int|depth|modulation)|filtenv|^filter env$|mod env depth"),
    ("modulation routing", r"lfo|voice depth|mod 2|audio mod|osc filter|filter osc|arpeggiator|slider"),
    ("resonance", r"resonance"),
    ("filter cutoff", r"cutoff|filter.*freq|f[12] frequency|vcf frequency|hpf|filter freq"),
    ("drive / distortion", r"drive|distortion|overdrive|feedback/ext"),
    ("effects", r"delay|chorus|reverb|effect|fxslot|fx "),
    ("envelope shape", r"sustain|decay|release|attack|\bsus\b|filter variation"),
    ("oscillator / noise mix", r"mixer|mix level|osc mix|noise|sub osc|sub level|ring|level vco|osc ?\d level|osc \d level|osc1 level"),
    ("oscillator character", r"shape|wave|color|hardness|sync|pulse|\bpw\b|density|detune|octave|tune|pitch|frequency|\bfm\b|range|semitone|tone mod|unisson|air|organ preset"),
]


def classify(name):
    lowered = name.lower().replace("&gt;", ">")
    for label, pattern in RULES:
        if re.search(pattern, lowered):
            return label
    return "other"


def percent(count, total):
    return f"{100 * count / total:3.0f}%"


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "library/hardware_presets.json"
    presets = [p for p in json.load(open(path)) if p["mappings"]]
    total = len(presets)
    print(f"{total} presets with mappings, {len({p['synth'] for p in presets})} synths, "
          f"{sum(len(p['mappings']) for p in presets)} mappings\n")

    per_preset = collections.Counter()
    per_synth = collections.defaultdict(set)
    per_sensor = collections.defaultdict(collections.Counter)
    spans = collections.defaultdict(list)
    sizes = collections.Counter()
    other_names = collections.Counter()
    for preset in presets:
        seen = set()
        sizes[len(preset["mappings"])] += 1
        for mapping in preset["mappings"]:
            label = classify(mapping["name"])
            seen.add(label)
            per_synth[label].add(preset["synth"])
            per_sensor[mapping["sensor"]][label] += 1
            spans[label].append(mapping["high"] - mapping["low"])
            if label == "other":
                other_names[mapping["name"]] += 1
        for label in seen:
            per_preset[label] += 1

    print("Presets that map each kind of control (a preset counts once):")
    for label, count in per_preset.most_common():
        median = statistics.median(spans[label])
        print(f"  {percent(count, total)}  {label:26} {count:3} presets, {len(per_synth[label])} synths, median travel {median:.0f} of 127")

    print("\nWhich control each of the Touché's four sensors drives (share of that sensor's mappings):")
    for sensor in sorted(per_sensor):
        counter = per_sensor[sensor]
        n = sum(counter.values())
        if n < 10:
            print(f"  sensor {sensor}: only {n} mappings, ignored")
            continue
        top = ", ".join(f"{label} {percent(c, n).strip()}" for label, c in counter.most_common(4))
        print(f"  sensor {sensor} ({n} mappings): {top}")

    print("\nMappings per preset:", dict(sorted(sizes.items())))
    print("\nNames left as 'other':", dict(other_names.most_common(12)))


main()
