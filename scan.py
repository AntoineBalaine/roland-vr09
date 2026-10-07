#!/usr/bin/env python3
"""Probe the undocumented address space of the VR-09 keyboard part with RQ1 over the raw MIDI device.

  scan.py snap NAME     read the first 16 x 128 x 128 addresses into dumps/scan_NAME.json (non-zero bytes only)
  scan.py diff A B      list the differences between two scans
"""
import json
import os
import select
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vr09

DEVICE_FILE = "/dev/snd/midiC2D0"


def request(fd, address, size, wait=0.04):
    body = list(address) + vr09.to_bytes(size)
    msg = vr09.header("kb", 0x11) + body + [vr09.checksum(body), 0xF7]
    while select.select([fd], [], [], 0)[0]:
        os.read(fd, 4096)
    os.write(fd, bytes(msg))
    raw = b""
    deadline = time.time() + 1
    while time.time() < deadline and select.select([fd], [], [], wait)[0]:
        raw += os.read(fd, 4096)
        if raw.endswith(b"\xf7"):
            break
    lo = vr09.from_bytes(address)
    return {a: v for a, v in vr09.parse_dt1(raw).items() if lo <= a < lo + size}


def snap(name):
    """Read 128 bytes from every (aa, bb, 00) start and keep the non-zero bytes (unmapped space reads as 0)."""
    fd = os.open(DEVICE_FILE, os.O_RDWR | os.O_NONBLOCK)
    result = {}
    for aa in range(16):
        for bb in range(128):
            values = request(fd, (aa, bb, 0), 128, wait=0.2)
            if len(values) < 128:
                print(f"incomplete read at {aa:02X} {bb:02X}: {len(values)} bytes", flush=True)
            result.update({f"{a:08X}": v for a, v in values.items() if v})
        print(f"done {aa:02X}: {len(result)} non-zero bytes so far", flush=True)
    json.dump(result, open(f"dumps/scan_{name}.json", "w"), sort_keys=True, indent=0)


def diff(a, b):
    da, db = (json.load(open(f"dumps/scan_{n}.json")) for n in (a, b))
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            address = " ".join(f"{x:02X}" for x in vr09.to_bytes(int(key, 16)))
            print(f"{address}  {da.get(key)} -> {db.get(key)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snap" and len(sys.argv) == 3:
        snap(sys.argv[2])
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
