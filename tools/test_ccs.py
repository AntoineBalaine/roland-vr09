#!/usr/bin/env python3
"""Listen to the CC targets of the Touché remap catalog on the real VR-09, one at a time.

  tools/test_ccs.py                 test every CC target nobody has judged yet
  tools/test_ccs.py ID [ID ...]     test these targets, even if they were judged before
  tools/test_ccs.py --list          list the CC targets and what was heard so far
  tools/test_ccs.py --dry-run       send no MIDI, only ask the questions (to try the script)
  tools/test_ccs.py --results FILE  keep the answers in FILE instead of library/target-tests.json

For each target the script puts a suitable sound on the keyboard, plays a chord, moves the CC from its lowest to its
highest value and back, and asks whether you heard a change. A CC cannot be read back from the keyboard, so only
an ear can judge it. The answers go to library/target-tests.json, the file the web pages use, and at the end the
catalog of targets and the mappings are regenerated from it.

The sounds: the upper part plays Super Saw Ld, the lower part plays the Sweep Pad of 12-3 DIMPnooBrill, and the
second piano layer ("Piano dual 2", channel 1) comes from 3-1 Chowii EP. The chorus sends are judged on Saw Lead 1,
a plain saw, because a supersaw already beats like a chorus, and the decay on a plucked string. Envelope and reverb controls are heard
on repeated short chords, because they shape the start and the end of a note, not a note being held.

Close the web pages' MIDI connection first: only one program can hold the VR-09's port.
"""
import datetime
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import vr09  # noqa: E402

TARGETS = "web/public/maps/targets.json"
DEFAULT_RESULTS = "library/target-tests.json"
CATALOG = "library/catalog.yaml"
NOTES = [60, 64, 67]
SWEEP_SECONDS = 5.0
STEP = 0.015

# Where each group of targets is heard: a library patch to recall, and a tone to write over its first part.
SETUPS = {
    "upper": {"label": "Super Saw Ld on the upper synth", "patch": "14-3_Native_Lead", "tone": ((1, 3, 1), (111, 13, 0))},
    "clean_upper": {"label": "Saw Lead 1 on the upper synth (a plain saw, no supersaw detune)", "patch": "14-3_Native_Lead", "tone": ((1, 3, 1), (111, 11, 0))},
    "pluck_upper": {"label": "Steel-str.Gt on the upper synth (a plucked string that rings and decays)", "patch": "14-3_Native_Lead", "tone": ((1, 3, 1), (61, 0, 0))},
    "lower": {"label": "the Sweep Pad of the lower synth (12-3 DIMPnooBrill)", "patch": "12-3_DIMPnooBrill", "tone": None},
    "clean_lower": {"label": "Saw Lead 1 on the lower synth (a plain saw, no supersaw detune)", "patch": "12-3_DIMPnooBrill", "tone": ((1, 0x13, 1), (111, 11, 0))},
    "piano2": {"label": "the second piano layer of 3-1 Chowii EP", "patch": "3-1_Chowii_EP", "tone": None},
}
GROUP_OF_CHANNEL = {4: "upper", 16: "upper", 3: "lower", 1: "piano2"}
GROUP_ORDER = ["upper", "clean_upper", "pluck_upper", "lower", "clean_lower", "piano2"]
# A chorus send is hard to hear on a supersaw, which already beats like a chorus, so it is judged on a plain saw.
# The decay is judged on a plucked string, where the time the sound takes to die away is easy to hear.
SETUP_OF_ID = {"cc-upper-chorus": "clean_upper", "cc-lower-chorus": "clean_lower", "cc-upper-decay": "pluck_upper"}
# "steps" plays four chords with the control at its minimum, maximum, minimum, maximum: (seconds held, seconds of silence after).
STEP_TIMING = {"cc-upper-decay": (3.5, 1.0)}
SCALE = 1.0  # shortened by --dry-run, which sends nothing and need not wait


def setup_of(target):
    return SETUP_OF_ID.get(target["id"]) or GROUP_OF_CHANNEL[target["channel"]]

# What to listen for. mode "hold" plays one long chord; "pulse" repeats short chords, because attack, decay, release and
# reverb tails only show at the start and the end of notes. A prelude sets other CCs first (vibrato rate needs vibrato depth).
HINTS = {
    "cc-upper-vibrato-rate": ("hold", "the speed of the pitch wobble (it is set to a clear depth first)", [(4, 77, 110)]),
    "cc-upper-reverb": ("pulse", "more room and a longer tail after each chord", []),
    "cc-upper-chorus": ("hold", "a plain saw turning thicker, wider and shimmering", []),
    "cc-upper-pan": ("hold", "the sound moving from the left speaker to the right", []),
    "cc-upper-release": ("pulse", "how long each chord lingers after the keys are released", []),
    "cc-upper-attack": ("pulse", "how quickly each chord fades in", []),
    "cc-upper-decay": ("steps", "the plucked string dying away fast at the minimum and slowly at the maximum", []),
    "cc-upper-modulation": ("hold", "a vibrato or wobble appearing, as with the modulation wheel", []),
    "cc-lower-cutoff": ("hold", "the brightness of the lower sound", []),
    "cc-lower-resonance": ("hold", "a whistling, peaky quality growing at the filter's edge", []),
    "cc-lower-release": ("pulse", "how long each chord lingers after the keys are released", []),
    "cc-lower-attack": ("pulse", "how quickly each chord fades in", []),
    "cc-lower-decay": ("pulse", "how quickly each chord drops after its first moment", []),
    "cc-lower-vibrato-depth": ("hold", "a pitch wobble appearing and deepening", []),
    "cc-lower-vibrato-rate": ("hold", "the speed of the pitch wobble (it is set to a clear depth first)", [(3, 77, 110)]),
    "cc-lower-modulation": ("hold", "a vibrato or wobble appearing, as with the modulation wheel", []),
    "cc-lower-reverb": ("pulse", "more room and a longer tail after each chord", []),
    "cc-lower-chorus": ("hold", "a plain saw turning thicker, wider and shimmering", []),
    "cc-lower-expression": ("hold", "the volume of the lower sound", []),
    "cc-piano-expression": ("hold", "the volume of the second piano layer", []),
    "cc-piano-reverb": ("pulse", "more room and a longer tail after each chord", []),
    "cc-piano-chorus": ("hold", "a thicker, wider, shimmering sound", []),
    "cc-master-expression": ("hold", "the overall volume", []),
}
DEFAULT_HINT = ("hold", "any change of the sound", [])

# A CC keeps its value until another one arrives, so these are put back to neutral before and after every test.
NEUTRAL_CHANNELS = [1, 3, 4, 16]
NEUTRAL_VALUES = [(121, 0), (11, 127), (1, 0), (10, 64), (71, 64), (72, 64), (73, 64), (74, 64), (75, 64), (76, 64), (77, 64)]


def pack(address):
    return (address[0] << 14) | (address[1] << 7) | address[2]


def send(fd, data):
    if fd is not None:
        os.write(fd, bytes(data))
        time.sleep(0.002)


def neutral(fd):
    for channel in NEUTRAL_CHANNELS:
        for number, value in NEUTRAL_VALUES:
            send(fd, [0xB0 | (channel - 1), number, value])


def chord(fd, channel, on):
    for note in NOTES:
        send(fd, [(0x90 if on else 0x80) | channel, note, 90 if on else 0])


def catalog_keys():
    """The patches of the library, read without a YAML library: keys are the two-space-indented lines under patches."""
    keys = []
    for line in open(CATALOG):
        match = re.match(r'^  "?([^\s":][^":]*)"?:\s*$', line)
        if match:
            keys.append(match.group(1))
    return keys


def load_sound(fd, state, group):
    if state.get("group") == group:
        return
    setup = SETUPS[group]
    print(f"\nSetting up the keyboard: {setup['label']}...", flush=True)
    if fd is not None:
        neutral(fd)
        vr09.recall_prepared(fd, state["dumps"], state["varying"], setup["patch"])
        if setup["tone"]:
            address, data = setup["tone"]
            vr09.dt1(fd, "kb", pack(address), list(data))
        time.sleep(0.4)
    state["group"] = group


def steps(fd, target, hint):
    """Four held chords with the control at its minimum, maximum, minimum and maximum, for envelope controls."""
    cc_channel = target["channel"] - 1
    note_channel = 3 if target["channel"] == 16 else cc_channel
    low, high = sorted((target["low"], target["high"]))
    hold, rest = STEP_TIMING.get(target["id"], (2.0, 1.0))
    for value in (low, high, low, high):
        print(f"      chord with the control at {value} ({'minimum' if value == low else 'maximum'})", flush=True)
        send(fd, [0xB0 | cc_channel, target["cc"], value])
        time.sleep(0.05 * SCALE)
        chord(fd, note_channel, True)
        time.sleep(hold * SCALE)
        chord(fd, note_channel, False)
        time.sleep(rest * SCALE)
    send(fd, [0xB0 | cc_channel, target["cc"], low])


def sweep(fd, target, hint):
    mode, _, prelude = hint
    if mode == "steps":
        return steps(fd, target, hint)
    cc_channel = target["channel"] - 1
    note_channel = 3 if target["channel"] == 16 else cc_channel
    low, high = sorted((target["low"], target["high"]))
    for channel, number, value in prelude:
        send(fd, [0xB0 | (channel - 1), number, value])
    send(fd, [0xB0 | cc_channel, target["cc"], low])
    if mode == "hold":
        chord(fd, note_channel, True)
    started = time.time()
    playing, last = mode == "hold", None
    while True:
        elapsed = time.time() - started
        phase = elapsed / (SWEEP_SECONDS * SCALE)
        if phase >= 1:
            break
        if mode == "pulse":
            on = (elapsed % 1.0) < 0.5
            if on != playing:
                chord(fd, note_channel, on)
                playing = on
        value = round(low + (phase * 2 if phase < 0.5 else (1 - phase) * 2) * (high - low))
        if value != last:
            send(fd, [0xB0 | cc_channel, target["cc"], value])
            last = value
        time.sleep(STEP)
    send(fd, [0xB0 | cc_channel, target["cc"], low])
    if playing:
        chord(fd, note_channel, False)
    time.sleep(1.2 * SCALE)  # the tail of the last chord


def read_results(path):
    return json.load(open(path)) if os.path.exists(path) else {}


def write_results(path, results):
    temporary = path + ".tmp"
    with open(temporary, "w") as f:
        json.dump(results, f, indent=2)
        f.write("\n")
    os.replace(temporary, path)


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        return "q"


def main():
    args = sys.argv[1:]
    global SCALE
    dry = "--dry-run" in args
    if dry:
        SCALE = 0.02
    results_path = DEFAULT_RESULTS
    if "--results" in args:
        at = args.index("--results")
        results_path = args[at + 1]
        del args[at:at + 2]
    args = [a for a in args if a != "--dry-run"]
    targets = [t for t in json.load(open(TARGETS)) if t["kind"] == "cc"]
    results = read_results(results_path)

    if args == ["--list"]:
        for t in targets:
            found = results.get(t["id"], {})
            heard = found.get("heard")
            print(f"{t['id']:26s} ch{t['channel']:2d} CC{t['cc']:<3d} {'works' if heard else 'no effect' if heard is False else 'not judged'}")
        return
    wanted = [t for t in targets if (t["id"] in args if args else "heard" not in results.get(t["id"], {}))]
    unknown = [a for a in args if a not in {t["id"] for t in targets}]
    if unknown:
        sys.exit(f"not a CC target of the catalog: {', '.join(unknown)}")
    wanted.sort(key=lambda t: GROUP_ORDER.index(setup_of(t)))
    if not wanted:
        print("Every CC target has been judged. Name targets to test them again.")
        return

    fd, state = None, {"group": None}
    if not dry:
        keys = [k for k in catalog_keys() if os.path.exists(f"dumps/{k}.json")]
        try:
            fd, state["dumps"], state["varying"] = vr09.prepare(keys)
        except RuntimeError as error:
            sys.exit(f"{error}\nClose the web pages' MIDI connection (the bridge page, the editor) and try again.")
    print(f"{len(wanted)} controls to listen to. Hold your hands off the Touché and the keys; the script plays the chords.")
    changed = False
    try:
        for index, target in enumerate(wanted, 1):
            hint = HINTS.get(target["id"], DEFAULT_HINT)
            group = setup_of(target)
            load_sound(fd, state, group)
            while True:
                print(f"\n[{index}/{len(wanted)}] {target['label']} (CC{target['cc']}, channel {target['channel']})")
                print(f"    Listen for: {hint[1]}.")
                if hint[0] == "steps":
                    print("    Four chords, the control at its minimum, maximum, minimum, maximum:", flush=True)
                else:
                    print(f"    Sweeping from {min(target['low'], target['high'])} to {max(target['low'], target['high'])} and back over {SWEEP_SECONDS:.0f} seconds"
                          f"{', on repeated short chords' if hint[0] == 'pulse' else ''}...", flush=True)
                sweep(fd, target, hint)
                neutral(fd)
                answer = ask("Did you hear a change?  [y] yes  [n] no  [r] repeat  [s] skip  [q] quit: ")
                if answer in ("r", "repeat", ""):
                    continue
                break
            if answer == "q":
                break
            if answer in ("y", "n"):
                results[target["id"]] = dict(results.get(target["id"], {}), kind="cc", label=target["label"], heard=answer == "y",
                                             at=datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
                                             heard_on=SETUPS[group]["label"])
                write_results(results_path, results)
                changed = True
                print(f"    Noted: {'a change was heard' if answer == 'y' else 'nothing was heard'}.")
    finally:
        if fd is not None:
            for channel in range(16):
                send(fd, [0xB0 | channel, 123, 0])  # all notes off
            neutral(fd)
            os.close(fd)

    judged = [t for t in targets if "heard" in results.get(t["id"], {})]
    print(f"\n{len(judged)} of {len(targets)} CC controls are judged. Answers are in {results_path}.")
    if changed and results_path == DEFAULT_RESULTS and not dry:
        print("Regenerating the targets and the mappings from the answers...")
        subprocess.run([sys.executable, "tools/make_templates.py"], check=False)


if __name__ == "__main__":
    main()
