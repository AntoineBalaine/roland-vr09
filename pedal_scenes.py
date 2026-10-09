#!/usr/bin/env python3
"""Switch VR-09 scenes with a Bluetooth page-turner pedal (e.g. Donner), next/previous through
an ordered setlist. The pedal is a Bluetooth HID keyboard, not MIDI, so pair it to this computer
like any Bluetooth keyboard first, then run this script.

  pedal_scenes.py setlist.txt [--device NAME] [--next KEY] [--prev KEY] [--dry-run]
  pedal_scenes.py --list-devices

setlist.txt: one dump name per line (matching dumps/<name>.json, the keys in library/catalog.yaml),
in performance order. Blank lines are ignored, and so is whatever follows a #. Make one with:
collect_library.py setlist.

The first press of next sends the first scene, the next presses go forward, prev goes back. Nothing is
sent at start-up.

  --device NAME   listen only to the keyboard whose name contains NAME (see --list-devices), and take it
                  over so its keys reach no other program. Without it every keyboard is listened to,
                  the laptop's included, so Page Up and Page Down there would switch scenes too.
  --next, --prev  key names, by default page_down and page_up (the Donner pedal's page mode); others are
                  names such as left, right, space, up, down, enter
  --dry-run       show what would be sent without touching the VR-09

Key presses are read from /dev/input with evdev, which works under Wayland and X11 and needs your user
to be in the input group.
"""
import os
import select
import sys
import time

import evdev
from evdev import ecodes

import vr09


def load_setlist(path):
    names = []
    with open(path) as f:
        for line in f:
            name = line.split("#", 1)[0].strip()  # whatever follows a # is a comment
            if name:
                names.append(name)
    missing = [n for n in names if not os.path.exists(f"dumps/{n}.json")]
    if missing:
        sys.exit(f"no dump for: {', '.join(missing)} (names are the keys in library/catalog.yaml)")
    return names


def key_code(name):
    code = ecodes.ecodes.get("KEY_" + name.replace("_", "").upper())
    if code is None:
        sys.exit(f"unknown key name: {name!r} (try page_down, page_up, left, right, space, enter)")
    return code


def keyboards(name_part, codes):
    """The input devices that have all of the given keys, and whose name contains name_part if given."""
    found = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError:
            continue
        has_keys = ecodes.EV_KEY in device.capabilities() and all(c in device.capabilities()[ecodes.EV_KEY] for c in codes)
        if has_keys and (not name_part or name_part.lower() in device.name.lower()):
            found.append(device)
        else:
            device.close()
    return found


def list_devices():
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
        except OSError as e:
            print(f"{path}: cannot be read ({e.strerror}); is your user in the input group?")
            continue
        if ecodes.EV_KEY in device.capabilities():
            print(f"{path}  {device.name!r}  {device.phys or ''}")
        device.close()


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args == ["--list-devices"]:
        return list_devices()
    setlist_path, rest = args[0], args[1:]
    next_name, prev_name, device_name, dry_run = "page_down", "page_up", None, False
    i = 0
    while i < len(rest):
        if rest[i] == "--next":
            next_name, i = rest[i + 1], i + 2
        elif rest[i] == "--prev":
            prev_name, i = rest[i + 1], i + 2
        elif rest[i] == "--device":
            device_name, i = rest[i + 1], i + 2
        elif rest[i] == "--dry-run":
            dry_run, i = True, i + 1
        else:
            sys.exit(f"unknown argument: {rest[i]}")

    setlist = load_setlist(setlist_path)
    if not setlist:
        sys.exit("setlist is empty")
    next_code, prev_code = key_code(next_name), key_code(prev_name)
    devices = keyboards(device_name, (next_code, prev_code))
    if not devices:
        sys.exit("no keyboard with those keys" + (f" and a name containing {device_name!r}" if device_name else "") + "; see --list-devices")
    if device_name:
        for device in devices:
            try:
                device.grab()  # nobody else gets this keyboard's keys
            except OSError as e:
                print(f"could not take over {device.name!r} ({e.strerror}), its keys also reach other programs", file=sys.stderr)

    # Load the setlist once: the addresses to write depend only on the scenes in it, so a key press
    # only has to send them.
    if dry_run:
        dumps = vr09.load_dumps(sorted(set(setlist)))
        fd, varying = None, vr09.varying_keys(list(dumps.values()))
    else:
        fd, dumps, varying = vr09.prepare(sorted(set(setlist)))
    print(f"{len(setlist)} scenes from {setlist_path}, {len(varying)} addresses differ between them")
    print("listening to: " + ", ".join(repr(d.name) for d in devices))
    print(f"waiting: {next_name} sends {setlist[0]}, {prev_name} goes back" + (" (dry run)" if dry_run else ""))

    index = -1  # nothing sent yet
    try:
        while True:
            ready, _, _ = select.select(devices, [], [])
            for device in ready:
                for event in device.read():
                    if event.type != ecodes.EV_KEY or event.value != 1:  # key down only, no auto-repeat
                        continue
                    if event.code == next_code:
                        index = min(len(setlist) - 1, index + 1)
                    elif event.code == prev_code:
                        index = max(0, index - 1)
                    else:
                        continue
                    name = setlist[index]
                    started = time.time()
                    if dry_run:
                        print(f"[{index + 1}/{len(setlist)}] {name}  (dry run, {len(vr09.groups(varying))} messages would be sent)")
                    else:
                        try:
                            vr09.recall_prepared(fd, dumps, varying, name)
                            print(f"[{index + 1}/{len(setlist)}] {name}  ({time.time() - started:.2f} s)")
                        except Exception as e:
                            print(f"[{index + 1}/{len(setlist)}] {name}: not sent ({e})", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        for device in devices:
            try:
                device.ungrab()
            except OSError:
                pass


if __name__ == "__main__":
    main()
