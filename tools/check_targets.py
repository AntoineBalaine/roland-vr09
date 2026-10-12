#!/usr/bin/env python3
"""Check the parameter-address targets of the Touché remap catalog on the real VR-09, without the web page.

  tools/check_targets.py                 check every address target
  tools/check_targets.py ID [ID ...]     check only these targets
  tools/check_targets.py --list          list the targets and what was found so far

For each target the script reads the address, writes a value at the other end of the target's range, reads
it back, and puts the original value back. The verdict is accepted (it reads back what was written),
refused (it did not change), changed to a different value (the unit clipped it), or no reply. The results
go to library/target-tests.json, the same file the web page's Target test keeps, so the page's table shows
them. At the end every original value is read once more, to prove that the unit is as it was.

CC targets are not checked here: a CC may change only the sound engine, which cannot be read back, and the
VR-09 offers no way to restore the previous value of a controller. They need listening (see the page).

Close the web page's MIDI connection first: only one program can hold the VR-09's port.
"""
import datetime
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import vr09  # noqa: E402

TARGETS = "web/public/maps/targets.json"
RESULTS = "library/target-tests.json"
SETTLE = 0.1  # seconds the unit gets to take a write before it is read back


def pack(address):
    return (address[0] << 14) | (address[1] << 7) | address[2]


def read(fd, address):
    return vr09.rq1(fd, tuple(address), 1).get(pack(address))


def check(fd, target, original):
    low, high = sorted((target["low"], target["high"]))
    value = low if original == high else high
    vr09.dt1(fd, "kb", pack(target["address"]), [value])
    time.sleep(SETTLE)
    readback = read(fd, target["address"])
    vr09.dt1(fd, "kb", pack(target["address"]), [original])
    time.sleep(SETTLE)
    restored = read(fd, target["address"]) == original
    if readback is None:
        verdict = "no reply after the write"
    elif readback == value:
        verdict = "accepted"
    elif readback == original:
        verdict = "refused: the value did not change"
    else:
        verdict = f"changed to a different value ({readback})"
    return {"kind": "dt1", "original": original, "sent": value, "readback": readback, "restored": restored, "verdict": verdict}


def main():
    args = sys.argv[1:]
    targets = json.load(open(TARGETS))
    results = json.load(open(RESULTS)) if os.path.exists(RESULTS) else {}
    if args == ["--list"]:
        for t in targets:
            found = results.get(t["id"], {})
            print(f"{t['id']:26s} {t['kind']:4s} {t['status']:11s} {found.get('verdict', 'not tested')}")
        return
    wanted = [t for t in targets if t["kind"] == "dt1" and (not args or t["id"] in args)]
    unknown = [a for a in args if a not in {t["id"] for t in wanted}]
    if unknown:
        sys.exit(f"not an address target of the catalog: {', '.join(unknown)}")

    fd = vr09.open_device(vr09.find_port())
    try:
        originals = {}
        for t in wanted:
            originals[t["id"]] = read(fd, t["address"])
        missing = [i for i, v in originals.items() if v is None]
        if missing:
            sys.exit(f"the VR-09 did not answer for: {', '.join(missing)}")
        counts = {}
        for i, t in enumerate(wanted, 1):
            result = check(fd, t, originals[t["id"]])
            result["label"] = t["label"]
            result["at"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            if "heard" in results.get(t["id"], {}):
                result["heard"] = results[t["id"]]["heard"]
            results[t["id"]] = result
            counts[result["verdict"]] = counts.get(result["verdict"], 0) + 1
            print(f"{i:2d}/{len(wanted)} {t['id']:26s} {t['status']:11s} {result['verdict']} (sent {result['sent']}, read back {result['readback']})")
        after = {t["id"]: read(fd, t["address"]) for t in wanted}
    finally:
        os.close(fd)

    temporary = RESULTS + ".tmp"
    with open(temporary, "w") as f:
        json.dump(results, f, indent=2)
        f.write("\n")
    os.replace(temporary, RESULTS)
    print()
    for verdict, n in sorted(counts.items(), key=lambda kv: -kv[1]):
        print(f"{n:3d} x {verdict}")
    changed = [i for i in originals if originals[i] != after[i]]
    print("every original value is back:", "yes" if not changed else "NO: " + ", ".join(f"{i} {originals[i]} -> {after[i]}" for i in changed))
    print(f"results written to {RESULTS}")


if __name__ == "__main__":
    main()
