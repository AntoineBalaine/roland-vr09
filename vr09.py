#!/usr/bin/env python3
"""Dump, diff and replay VR-09 state over USB MIDI using RQ1/DT1 (no dependencies besides amidi).

  vr09.py ports
  vr09.py dump NAME     read every block in BLOCKS into dumps/NAME.json
  vr09.py diff A B      list the addresses whose values differ between two dumps
  vr09.py apply A B     write the values of dump A that differ from dump B to the keyboard (DT1)
  vr09.py watch         dump repeatedly and print every change as it happens
"""
import json
import os
import subprocess
import sys
import tempfile
import time

DEVICE = 0x10
# Keyboard part: model 62H with 3-byte addresses and sizes. Synth section: model 00 00 71H with 4-byte ones.
KINDS = {
    "kb": {"model": [0x62], "length": 3},
    "synth": {"model": [0x00, 0x00, 0x71], "length": 4},
}

# (name, start address, size, kind). Sizes are derived from the highest offset in the
# Parameter Address Map and may need adjusting if the unit does not answer.
BLOCKS = [
    ("system", (0x00, 0x00, 0x00), 0x69, "kb"),
    ("upper_piano", (0x01, 0x01, 0x00), 0x65, "kb"),
    ("upper_synth_dual2", (0x01, 0x02, 0x00), 0x65, "kb"),
    ("upper_synth", (0x01, 0x03, 0x00), 0x65, "kb"),
    ("lower_piano", (0x01, 0x11, 0x00), 0x65, "kb"),
    ("lower_synth", (0x01, 0x13, 0x00), 0x65, "kb"),
    ("upper_piano_dual2", (0x01, 0x31, 0x00), 0x65, "kb"),
    ("drum", (0x01, 0x41, 0x00), 0x65, "kb"),
    ("organ_upper", (0x02, 0x00, 0x00), 0x3A, "kb"),
    ("organ_lower", (0x02, 0x01, 0x00), 0x3A, "kb"),
    ("organ_pedal", (0x02, 0x02, 0x00), 0x3A, "kb"),
    ("synth_set_upper2", (0x18, 0x00, 0x21, 0x00), 0x09, "synth"),
    ("synth_set_upper1", (0x18, 0x00, 0x22, 0x00), 0x09, "synth"),
    ("synth_set_lower", (0x18, 0x00, 0x25, 0x00), 0x09, "synth"),
]
KIND_OF = {name: kind for name, _, _, kind in BLOCKS}


def checksum(data):
    return (128 - sum(data) % 128) % 128


def to_bytes(value, length=3):
    return [(value >> (7 * i)) & 0x7F for i in reversed(range(length))]


def from_bytes(data):
    value = 0
    for b in data:
        value = (value << 7) | b
    return value


def header(kind, command):
    return [0xF0, 0x41, DEVICE] + KINDS[kind]["model"] + [command]


def send(port, msg, reply_file=None):
    args = ["amidi", "-p", port, "-S", " ".join(f"{b:02X}" for b in msg)]
    if reply_file:
        args += ["-r", reply_file, "-t", "1"]
    subprocess.run(args, capture_output=True)


def find_port():
    out = subprocess.run(["amidi", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines()[1:]:
        if "VR-09" in line:
            return line.split()[1]
    sys.exit("VR-09 not found, check the USB cable")


def rq1(port, address, size, kind="kb"):
    length = KINDS[kind]["length"]
    body = list(address) + to_bytes(size, length)
    msg = header(kind, 0x11) + body + [checksum(body), 0xF7]
    with tempfile.NamedTemporaryFile() as out:
        send(port, msg, out.name)
        raw = open(out.name, "rb").read()
    lo = from_bytes(address)
    return {a: v for a, v in parse_dt1(raw, kind).items() if lo <= a < lo + size}


def parse_dt1(raw, kind="kb"):
    """Return {address: byte} for every DT1 message of the given kind found in raw."""
    prefix = [0x41, DEVICE] + KINDS[kind]["model"] + [0x12]
    length = KINDS[kind]["length"]
    start = len(prefix)
    values = {}
    for chunk in raw.split(b"\xf0")[1:]:
        msg = list(chunk.split(b"\xf7")[0])
        if msg[:start] != prefix:
            continue
        address, data, cks = from_bytes(msg[start : start + length]), msg[start + length : -1], msg[-1]
        if checksum(msg[start:-1]) != cks:
            print(f"bad checksum in reply at {address:06X}", file=sys.stderr)
            continue
        for i, b in enumerate(data):
            values[address + i] = b
    return values


def snapshot(port, verbose=False):
    result = {}
    for block, start, size, kind in BLOCKS:
        values = rq1(port, start, size, kind)
        if verbose:
            print(f"{block:20s} {len(values)}/{size} bytes")
        result.update({f"{block}:{a:08X}": v for a, v in values.items()})
    return result


def dump(name):
    result = snapshot(find_port(), verbose=True)
    os.makedirs("dumps", exist_ok=True)
    with open(f"dumps/{name}.json", "w") as f:
        json.dump(result, f, indent=0, sort_keys=True)


def watch():
    port = find_port()
    previous = snapshot(port)
    print("watching, change something on the keyboard", flush=True)
    while True:
        current = snapshot(port)
        for key in sorted(set(previous) | set(current)):
            if previous.get(key) != current.get(key):
                print(f"{key}  {previous.get(key)} -> {current.get(key)}", flush=True)
        previous = current


def dt1(port, kind, address, data):
    body = to_bytes(address, KINDS[kind]["length"]) + data
    send(port, header(kind, 0x12) + body + [checksum(body), 0xF7])
    time.sleep(0.05)


def groups(changed):
    """Turn changed keys into (block, start address, length) writes.

    Addresses marked # in the map cannot start a message, so the reverb level goes with the reverb
    type, and the bank bytes go with the tone number.
    """
    base = {name: from_bytes(start) for name, start, _, _ in BLOCKS}
    result = set()
    for key in changed:
        block, address = key.split(":")
        address = int(address, 16)
        offset = address - base[block]
        if block == "system" and offset in (0, 1):
            result.add((block, base[block], 2))
        elif block.startswith(("upper_", "lower_", "drum")) and offset in (1, 2, 3):
            result.add((block, base[block] + 1, 3))
        else:
            result.add((block, address, 1))
    return sorted(result)


def apply(a, b):
    """Send the values of dump a that differ from dump b."""
    da, db = (json.load(open(f"dumps/{n}.json")) for n in (a, b))
    port = find_port()
    changed = [k for k in sorted(da) if da[k] != db.get(k)]
    writes = groups(changed)
    for block, start, length in writes:
        data = [da[f"{block}:{start + i:08X}"] for i in range(length)]
        dt1(port, KIND_OF[block], start, data)
    print(f"sent {len(writes)} messages for {len(changed)} changed values")


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
    elif cmd == "apply" and len(sys.argv) == 4:
        apply(sys.argv[2], sys.argv[3])
    elif cmd == "watch":
        watch()
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
