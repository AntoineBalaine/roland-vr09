#!/usr/bin/env python3
"""Probe the undocumented address space of the VR-09 keyboard part with RQ1 (reads only).

  scan.py snap NAME FIRST LAST   read 128 bytes from every (aa, bb, 00) for aa in FIRST..LAST (hex)
                                 into dumps/scan_NAME.json, non-zero bytes only
  scan.py probe                  show how the synth section answers known and unknown addresses
  scan.py models                 send a one-byte RQ1 to every 1- to 4-byte model ID, log replies
  scan.py diff A B               list the differences between two scans

Reads are spaced GAP apart, results are saved after each address group, and the scan stops at the
first read that gets no reply, because a burst of reads to undefined addresses once made the unit
stop answering until it was restarted.
"""
import json
import os
import select
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import vr09

GAP = 0.02


def request(fd, address, size):
    body = list(address) + vr09.to_bytes(size)
    msg = vr09.header("kb", 0x11) + body + [vr09.checksum(body), 0xF7]
    while select.select([fd], [], [], 0)[0]:
        os.read(fd, 4096)
    os.write(fd, bytes(msg))
    raw = b""
    deadline = time.time() + 1
    while time.time() < deadline and select.select([fd], [], [], 0.2)[0]:
        raw += os.read(fd, 4096)
        if raw.endswith(b"\xf7"):
            break
    lo = vr09.from_bytes(address)
    return {a: v for a, v in vr09.parse_dt1(raw).items() if lo <= a < lo + size}


def snap(name, first, last):
    fd = vr09.open_device(vr09.find_port())
    path = f"dumps/scan_{name}.json"
    result = json.load(open(path)) if os.path.exists(path) else {}
    for aa in range(first, last + 1):
        for bb in range(128):
            values = request(fd, (aa, bb, 0), 128)
            if not values:
                time.sleep(1)
                values = request(fd, (aa, bb, 0), 128)
            if not values:
                json.dump(result, open(path, "w"), sort_keys=True, indent=0)
                sys.exit(f"no reply at {aa:02X} {bb:02X} 00, stopping (results so far saved)")
            if len(values) < 128:
                print(f"incomplete read at {aa:02X} {bb:02X}: {len(values)} bytes", flush=True)
            result.update({f"{a:08X}": v for a, v in values.items() if v})
            time.sleep(GAP)
        json.dump(result, open(path, "w"), sort_keys=True, indent=0)
        found = sum(1 for k in result if int(k, 16) >> 14 == aa)
        print(f"done {aa:02X}: {found} non-zero bytes in this group", flush=True)


def alive(fd):
    """True when the unit still answers an identity request."""
    while select.select([fd], [], [], 0)[0]:
        os.read(fd, 4096)
    os.write(fd, bytes([0xF0, 0x7E, 0x7F, 0x06, 0x01, 0xF7]))
    raw = b""
    deadline = time.time() + 1
    while time.time() < deadline and select.select([fd], [], [], 0.2)[0]:
        raw += os.read(fd, 4096)
        if b"\xf0\x7e\x10\x06\x02" in raw:
            return True
    return False


def probe():
    """Show how the synth section (model 00 00 71) answers known and unknown addresses."""
    fd = vr09.open_device(vr09.find_port())
    probes = [
        ((0x18, 0, 0x21, 0), 9), ((0x18, 0, 0, 0), 1), ((0x18, 0, 0, 0), 0x40),
        ((0x19, 0x41, 0, 0), 1), ((0x19, 0x41, 0, 0), 0x3D), ((0x19, 0x41, 0, 0), 0x40),
        ((0x19, 0x41, 1, 0), 0x3D), ((0x19, 0x21, 0, 0), 1), ((0x1A, 0x21, 0, 0), 1),
        ((0x17, 0, 0, 0), 1), ((0, 0, 0, 0), 1), ((0x20, 0, 0, 0), 1),
    ]
    for address, size in probes:
        values = vr09.rq1(fd, address, size, "synth")
        label = " ".join(f"{x:02X}" for x in address)
        print(f"{label} size {size:02X}: " + (f"{len(values)} bytes {list(values.values())[:12]}" if values else "no reply"), flush=True)
        time.sleep(0.05)
    print("unit still answers:", alive(fd))


def models():
    """Send a one-byte RQ1 to every 1- to 4-byte model ID and log any Roland reply."""
    fd = vr09.open_device(vr09.find_port())
    known = ([0x62], [0x00, 0x00, 0x71])
    candidates = [m for x in range(128) for m in ([x], [0, x], [0, 0, x], [0, 0, 0, x]) if m not in known]
    found = []
    for i, model in enumerate(candidates):
        if i % 32 == 0 and not alive(fd):
            sys.exit(f"unit stopped answering before model {model}, stopping")
        for length in (3, 4):
            body = [0] * length + vr09.to_bytes(1, length)
            msg = [0xF0, 0x41, vr09.DEVICE] + model + [0x11] + body + [vr09.checksum(body), 0xF7]
            while select.select([fd], [], [], 0)[0]:
                os.read(fd, 4096)
            os.write(fd, bytes(msg))
            raw = b""
            deadline = time.time() + 0.08
            while time.time() < deadline and select.select([fd], [], [], 0.02)[0]:
                raw += os.read(fd, 4096)
            replies = [b"\xf0" + c.split(b"\xf7")[0] + b"\xf7" for c in raw.split(b"\xf0")[1:] if c.startswith(b"\x41")]
            if replies:
                found.append((model, length, [r.hex(" ") for r in replies]))
                print(f"model {bytes(model).hex(' ')} ({length}-byte address): {replies[0].hex(' ')}", flush=True)
            time.sleep(GAP)
    print(f"{len(candidates)} model IDs probed, {len(found)} answered")
    json.dump(found, open("dumps/models.json", "w"), indent=1)


def diff(a, b):
    da, db = (json.load(open(f"dumps/scan_{n}.json")) for n in (a, b))
    for key in sorted(set(da) | set(db)):
        if da.get(key) != db.get(key):
            address = " ".join(f"{x:02X}" for x in vr09.to_bytes(int(key, 16)))
            print(f"{address}  {da.get(key)} -> {db.get(key)}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "snap" and len(sys.argv) == 5:
        snap(sys.argv[2], int(sys.argv[3], 16), int(sys.argv[4], 16))
    elif cmd == "probe":
        probe()
    elif cmd == "models":
        models()
    elif cmd == "diff" and len(sys.argv) == 4:
        diff(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)
