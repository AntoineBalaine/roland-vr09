#!/usr/bin/env python3
"""Switch VR-09 scenes with a Bluetooth page-turner pedal (e.g. Donner), next/previous through
an ordered setlist. The pedal is a Bluetooth HID keyboard, not MIDI, so pair it to this computer
like any Bluetooth keyboard first, then run this script.

  pedal_scenes.py setlist.txt
  pedal_scenes.py setlist.txt --next page_down --prev page_up

setlist.txt: one dump name per line (matching dumps/<name>.json), in performance order. Blank
lines and lines starting with # are ignored.

Key names default to page_down / page_up, matching the Donner pedal's Page Up/Page Down mode.
Use any name from pynput.keyboard.Key (e.g. left, right, space) to match a different pedal mode.

Needs the pynput package (pip install pynput). On Linux, global key capture needs an X11 session;
it will not see key presses under Wayland without extra setup.
"""
import sys

from pynput import keyboard

import vr09


def load_setlist(path):
    with open(path) as f:
        return [line.strip() for line in f if line.strip() and not line.startswith("#")]


def resolve_key(name):
    try:
        return keyboard.Key[name]
    except KeyError:
        sys.exit(f"unknown key name: {name!r} (see pynput.keyboard.Key for valid names)")


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    setlist_path = args[0]
    next_name, prev_name = "page_down", "page_up"
    i = 1
    while i < len(args):
        if args[i] == "--next":
            next_name = args[i + 1]
            i += 2
        elif args[i] == "--prev":
            prev_name = args[i + 1]
            i += 2
        else:
            sys.exit(f"unknown argument: {args[i]}")

    setlist = load_setlist(setlist_path)
    if not setlist:
        sys.exit("setlist is empty")
    next_key, prev_key = resolve_key(next_name), resolve_key(prev_name)
    index = 0

    # Load the setlist once: the addresses to write depend only on the scenes in it, so a key press
    # only has to send them.
    fd, dumps, varying = vr09.prepare(sorted(set(setlist)))
    print(f"{len(setlist)} scenes loaded from {setlist_path}, {len(varying)} addresses differ between them")
    print(f"[{index + 1}/{len(setlist)}] {setlist[index]} (not sent yet, press {next_name} or {prev_name})")

    def on_press(key):
        nonlocal index
        if key == next_key:
            index = min(len(setlist) - 1, index + 1)
        elif key == prev_key:
            index = max(0, index - 1)
        else:
            return
        name = setlist[index]
        print(f"[{index + 1}/{len(setlist)}] {name}")
        vr09.recall_prepared(fd, dumps, varying, name)

    with keyboard.Listener(on_press=on_press) as listener:
        listener.join()


if __name__ == "__main__":
    main()
