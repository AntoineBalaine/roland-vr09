#!/usr/bin/env python3
"""Dump and diff VR-09 state over USB MIDI using RQ1 requests (no dependencies besides amidi).

  vr09.py ports
  vr09.py dump NAME     read every block in BLOCKS into dumps/NAME.json
  vr09.py diff A B      list the addresses whose values differ between two dumps
"""
import json
import os
import subprocess
import sys
import tempfile

MODEL = 0x62
DEVICE = 0x10

# (name, start address, size). Sizes are derived from the highest offset in the
# Parameter Address Map and may need adjusting if the unit does not answer.
BLOCKS = [
    ("system", (0x00, 0x00, 0x00), 0x69),
    ("upper_piano", (0x01, 0x01, 0x00), 0x65),
    ("upper_synth_dual2", (0x01, 0x02, 0x00), 0x65),
    ("upper_synth", (0x01, 0x03, 0x00), 0x65),
    ("lower_piano", (0x01, 0x11, 0x00), 0x65),
    ("lower_synth", (0x01, 0x13, 0x00), 0x65),
    ("upper_piano_dual2", (0x01, 0x31, 0x00), 0x65),
    ("drum", (0x01, 0x41, 0x00), 0x65),
    ("organ_upper", (0x02, 0x00, 0x00), 0x3A),
    ("organ_lower", (0x02, 0x01, 0x00), 0x3A),
    ("organ_pedal", (0x02, 0x02, 0x00), 0x3A),
]


def checksum(data):
    return (128 - sum(data) % 128) % 128


def to_bytes(value, length=3):
    return [(value >> (7 * i)) & 0x7F for i in reversed(range(length))]


def from_bytes(data):
    value = 0
    for b in data:
        value = (value << 7) | b
    return value


def find_port():
    out = subprocess.run(["amidi", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if "VR-09" in line:
            return line.split()[1]
    sys.exit("VR-09 not found, check the USB cable")


def rq1(port, address, size):
    body = list(address) + to_bytes(size)
    msg = [0xF0, 0x41, DEVICE, MODEL, 0x11] + body + [checksum(body), 0xF7]
    with tempfile.NamedTemporaryFile() as out:
        subprocess.run(
            ["amidi", "-p", port, "-S", " ".join(f"{b:02X}" for b in msg), "-r", out.name, "-t", "1"],
            capture_output=True,
        )
        raw = open(out.name, "rb").read()
    return parse_dt1(raw)


def parse_dt1(raw):
    """Return {address: byte} for every DT1 message found in raw."""
    values = {}
    for chunk in raw.split(b"\xf0")[1:]:
        msg = list(chunk.split(b"\xf7")[0])
        if msg[:4] != [0x41, DEVICE, MODEL, 0x12]:
            continue
        address, data, cks = from_bytes(msg[4:7]), msg[7:-1], msg[-1]
        if checksum(msg[4:-1]) != cks:
            print(f"bad checksum in reply at {address:06X}", file=sys.stderr)
            continue
        for i, b in enumerate(data):
            values[address + i] = b
    return values


def dump(name):
    port = find_port()
    result = {}
    for block, start, size in BLOCKS:
        values = rq1(port, start, size)
        print(f"{block:20s} {len(values)}/{size} bytes")
        result.update({f"{block}:{a:06X}": v for a, v in values.items()})
    os.makedirs("dumps", exist_ok=True)
    with open(f"dumps/{name}.json", "w") as f:
        json.dump(result, f, indent=0, sort_keys=True)


def diff(a, b):
    da, db = (json.load(open(f"dumps/{n}.json")) for n in (a, b))
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            print(f"{key}  {da.get(key)} -> {db.get(key)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "ports":
        print(find_port())
    elif cmd == "dump" and len(sys.argv) == 3:
        dump(sys.argv[2])
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
