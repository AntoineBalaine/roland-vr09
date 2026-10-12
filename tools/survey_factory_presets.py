#!/usr/bin/env python3
"""Survey how Lié's preset designers shape the Touché's controls, to guide the remap presets of the bridge.

  survey_factory_presets.py [PRESET_DIR]

A macro ties one sensor (sensorIndex 0 to 4, or 5 for none) to one target (parameterId), with a range
(min and max, from 0 to 1) and a named curve. This script reads the macros of every .tem file under
PRESET_DIR (by default the Factory Presets of the macOS install) and prints how often each sensor is used,
how wide the ranges are, which curves are chosen, and how the presets are tagged.
"""
import collections
import os
import sys
import xml.etree.ElementTree as ET

DEFAULT_DIR = "/Library/Audio/Presets/ExpressiveE/Lie/Presets/Factory Presets"
NO_SENSOR = 5


def mapped_macros(tree):
    """Yield (sensor, min, max, curve) for every macro that is driven by a sensor and has a target."""
    for macro in tree.iter("MACRO"):
        sensor_text = macro.get("sensorIndex")
        parameter = macro.get("parameterId")
        if sensor_text is None or parameter is None or int(float(sensor_text)) == NO_SENSOR or float(parameter) < 0:
            continue
        sensor = int(float(sensor_text))  # Some files write 0.0 and others 0 for the same sensor.
        yield sensor, float(macro.get("min", 0)), float(macro.get("max", 1)), macro.get("presetNameToDisplay", "default")


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    tags = collections.Counter()
    sensors = collections.Counter()
    curves = collections.Counter()
    widths = collections.Counter()
    targets_per_preset = []
    inverted = 0
    files = 0
    for folder, _, names in os.walk(root):
        for name in names:
            if not name.endswith(".tem"):
                continue
            tree = ET.parse(os.path.join(folder, name))
            files += 1
            count = 0
            for sensor, low, high, curve in mapped_macros(tree):
                count += 1
                sensors[sensor] += 1
                curves[curve] += 1
                widths["full range (0 to 1)" if (low, high) == (0.0, 1.0) else "reduced or inverted"] += 1
                inverted += 1 if low > high else 0
            targets_per_preset.append(count)
            for tag in tree.iter("TAG"):
                tags[tag.get("name")] += 1

    print(f"{files} presets, {sum(targets_per_preset)} sensor-driven macros")
    print("\nmapped targets per preset:", dict(sorted(collections.Counter(targets_per_preset).items())))
    print("\nmacros per sensor:", dict(sorted(sensors.items())))
    print("\nranges:", dict(widths), f"(inverted: {inverted})")
    print("\ncurves:")
    for curve, count in curves.most_common():
        print(f"  {count:5}  {curve}")
    print("\ntags:")
    for tag, count in tags.most_common():
        print(f"  {count:5}  {tag}")


main()
