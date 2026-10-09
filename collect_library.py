#!/usr/bin/env python3
"""Interactively build a library of VR-09 patches: a dump, a photo of the screen, and a short audio
preview that the tool plays itself over MIDI, one patch at a time.

  collect_library.py capture [options]        run the interactive loop
  collect_library.py preview NAME [STYLE]     record the audio preview of a patch again (the keyboard
                                              must be on that patch)
  collect_library.py photo [--cam SOURCE] [--crop X,Y,W,H] [--exposure N]
                                              take one photo into library/photos/test.jpg and print
                                              what the OCR reads, to set up the camera
  collect_library.py reread [--all]           read the saved photos again to refresh tone, effect and level
                                              (titles are never touched; reviewed entries are skipped
                                              unless --all)
  collect_library.py serve [--port N] [--no-browser] [--setlist FILE]
                                              the library as a web page at http://127.0.0.1:8765/ (an Astro
                                              app in web/, run once with: cd web && npm install). Photo,
                                              fields and audio of every patch: double-click a card to edit
                                              it, click its reviewed flag to toggle it, and build the setlist
                                              (default setlist.txt) in the Setlist tab. Every change is saved
                                              at once; a new title renames the patch's files. Writes are
                                              refused while a capture is running. Same as: cd web && npm start
  collect_library.py setlist [FILE]           write a setlist file with every patch in order (default
                                              setlist.txt) for pedal_scenes.py
  collect_library.py sync                     after editing titles in library/catalog.yaml, rename the keys and
                                              files to match them
  collect_library.py unnamed                  list the patches still named unnamed_...
  collect_library.py rename OLD NEW           give a patch its real name (files and catalog follow)
  collect_library.py devices                  list the audio inputs

capture options:
  --cam SOURCE         camera: a webcam device such as /dev/video0, or the URL of a phone's JPEG snapshot
  --crop X,Y,W,H       keep only this pixel rectangle of the photo (the screen)
  --exposure N         webcam exposure time in units of 0.1 ms (default 40, or VR09_EXPOSURE); too high
                       and the bright screen turns white
  --no-camera          skip the photo, type the name instead
  --audio-device NAME  input to record from: part of its name, such as Scarlett, or its number
                       (default: VR09_AUDIO_DEVICE, then the system default input, often the laptop
                       microphone)
  --style STYLE        default preview style, see below (default chord)
  --auto               ask nothing but "recall the next patch, press Enter" (q to stop): the name is the one
                       read from the screen, and the preview uses the default style
  --start BANK-SLOT    the slot of the first patch, such as 5-1 (default: the one after the latest captured
                       patch in the catalog). The tool counts the slots itself, --per-bank N of them in a
                       bank (default 4); type a slot such as 2-3 at the prompt to jump to it
  --no-vision          do not read the screen with the API; patches get a placeholder name
  --vision-model M     model that reads the screen (default claude-haiku-4-5, or VR09_VISION_MODEL)
  --no-audio           skip the audio preview

Preview styles. The tool sends the notes to the pedal, lower and upper parts (MIDI channels 2, 3 and 4 in
Mode 2) for half a second, records until the tail has died, cuts the silence at both ends, keeps at
most 2 seconds and fades the end out. Only the parts the patch uses make a sound.
  chord   C major triad around middle C         pad     wide C major chord from C3
  bass    one low C (C2)                        lead    one G4
  drums   kick, hi-hat, snare, hi-hat on the drum part (MIDI channel 11); chosen by itself in --auto when
          the screen shows a "Kit"
  m       you play on the keyboard (4 s recording)
  48,55   any MIDI note numbers, separated by commas
  s       skip the preview

Each captured patch writes:
  dumps/<key>.json          parameter dump, same format as vr09.py dump
  library/photos/<key>.jpg  the screen photo (if a camera was used)
  library/audio/<key>.wav   the audio preview
  library/catalog.yaml      one entry per patch, meant to be edited by hand; the three files above are
                            found from the entry's key, so rename entries with the rename command

The screen is read by sending its photo to the Anthropic API, because Tesseract cannot read this small
bitmap font. The key is ANTHROPIC_API_KEY, taken from the environment or from the file named by
VR09_ENV_FILE (default ~/.env, of which only the needed lines are read). A key that is not tied to a
workspace also needs ANTHROPIC_WORKSPACE_ID (wrkspc_...), sent as the anthropic-workspace-id header. Entries read this way get
"reviewed: false" in the catalog: check the title, set it to true, then run sync if you changed it.

Dependencies beyond the standard library, installed in .venv: anthropic, pyyaml, numpy, sounddevice,
soundfile, pillow, and requests (phone camera). Each is only imported when the feature that needs it
is used.

Camera: a webcam is the simplest. It is read with ffmpeg (a system package, no Python module), so
--cam /dev/video0 is all it takes; the default is /dev/video0 when that device exists. Otherwise any
Android IP-camera app that serves a JPEG snapshot over HTTP works (the common "IP Webcam" app's
default snapshot URL is http://<phone-ip>:8080/shot.jpg). Set VR09_CAM or pass --cam to choose.
"""
import base64
import datetime
import json
import os
import re
import subprocess
import sys
import time

import vr09

EXPOSURE = int(os.environ.get("VR09_EXPOSURE", "40"))
VISION_MODEL = os.environ.get("VR09_VISION_MODEL", "claude-haiku-4-5")
ENV_FILE = os.environ.get("VR09_ENV_FILE", os.path.expanduser("~/.env"))
SCREEN_PROMPT = (
    "The first image is a photo of the LCD screen of a Roland VR-09 keyboard, showing a registration; the "
    "second is the same screen's title row enlarged. Read it exactly as displayed, keeping upper and lower "
    "case. Take care with characters that look alike, such as O and 0, l and I, 5 and S. Reply with only a "
    "JSON object with these string fields: "
    '"slot": the registration number in the highlighted box at the top left, such as 1-1; '
    '"name": the registration name next to it; '
    '"tone": the sound names on the lines under the title, without the numbers at the right; a layered '
    "patch has two lines, marked 1 and 2 in small boxes, so join them with ' + ' (for example "
    "'Saw Lead 1 + Super Saws'); a drum kit has a single line; "
    '"effect": the text after MFX: on the bottom line; '
    '"level": the numbers shown at the right of the sound lines, line by line, joined with \' / \' '
    "(for example '0 10 / -2 12'); "
    '"other": any other text on the screen that the fields above do not cover. '
    'Use "" for anything you cannot see.'
)
LIBRARY = "library"
PHOTOS = os.path.join(LIBRARY, "photos")
AUDIO = os.path.join(LIBRARY, "audio")
CATALOG = os.path.join(LIBRARY, "catalog.yaml")
OLD_CATALOG = os.path.join(LIBRARY, "catalog.json")
DEFAULT_CAM = os.environ.get("VR09_CAM") or os.environ.get("VR09_CAM_URL") or (
    "/dev/video0" if os.path.exists("/dev/video0") else "http://192.168.1.50:8080/shot.jpg"
)

# Preview: MIDI channels 2, 3 and 4 (zero-based 1, 2, 3) are the pedal, lower and upper parts in Mode 2.
PREVIEW_CHANNELS = (1, 2, 3)
PREVIEW_VELOCITY = 90
DRUMS = "drums"
DRUM_CHANNEL = 10   # MIDI channel 11 is the drum part in Mode 2
DRUM_PATTERN = [36, 42, 38, 42]  # kick, closed hi-hat, snare, closed hi-hat, a quarter second apart
STYLES = {"chord": [60, 64, 67], "pad": [48, 55, 64, 67], "bass": [36], "lead": [67], "drums": DRUMS}
NOTE_LENGTH = 0.5   # seconds the notes are held
LEAD_IN = 0.4       # seconds of recording before the notes, so the interface's start-up click is skipped
SKIP = 0.15         # seconds at the start of the recording that are ignored when looking for sound
MAX_LENGTH = 2.0    # longest preview kept
FADE_IN = 0.005
FADE_OUT = 0.25
SOUND_DB = -50      # a 20 ms stretch quieter than this (RMS, dBFS) counts as silence


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def safe(name):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in name)


def files(key):
    return {
        "dump": f"dumps/{key}.json",
        "photo": os.path.join(PHOTOS, f"{key}.jpg"),
        "audio": os.path.join(AUDIO, f"{key}.wav"),
    }


# Catalog ---------------------------------------------------------------------------------------


def load_catalog():
    """Return {key: entry}. A catalog.json from an earlier version is converted once."""
    import yaml

    if not os.path.exists(CATALOG) and os.path.exists(OLD_CATALOG):
        with open(OLD_CATALOG) as f:
            old = json.load(f)
        patches = {
            e["name"]: {
                "title": e.get("display_name", ""),
                "captured": e.get("captured_at", ""),
                "preview": "manual",
                "tags": [],
                "notes": "",
                "ocr_hint": e.get("ocr_text", ""),
            }
            for e in old
        }
        save_catalog(patches)
        os.remove(OLD_CATALOG)
        print(f"converted {OLD_CATALOG} to {CATALOG}")
        return patches
    if not os.path.exists(CATALOG):
        return {}
    with open(CATALOG) as f:
        patches = (yaml.safe_load(f) or {}).get("patches") or {}
    for entry in patches.values():
        entry["captured"] = str(entry.get("captured", ""))
    return patches


def save_catalog(patches):
    import yaml

    os.makedirs(LIBRARY, exist_ok=True)
    temporary = CATALOG + ".tmp"
    with open(temporary, "w") as f:
        f.write(
            "# Patch library, written by collect_library.py. Edit title, tags and notes freely.\n"
            "# The key of an entry is the stem of its files: dumps/<key>.json, library/photos/<key>.jpg and\n"
            "# library/audio/<key>.wav. To rename an entry, use: collect_library.py rename OLD NEW\n"
        )
        yaml.safe_dump({"patches": patches}, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)
    os.replace(temporary, CATALOG)  # a crash cannot leave half a catalog


def rename(old, new):
    """Give a captured patch its real name: the dump, photo, audio and the catalog entry follow."""
    patches = load_catalog()
    if old not in patches:
        sys.exit(f"no patch named {old!r} in {CATALOG}")
    new_key = safe(new)
    if new_key in patches or os.path.exists(files(new_key)["dump"]):
        sys.exit(f"{new_key!r} already exists")
    for kind, path in files(old).items():
        if os.path.exists(path):
            os.replace(path, files(new_key)[kind])
    entry = patches.pop(old)
    entry["title"] = new
    patches[new_key] = entry
    save_catalog(patches)
    print(f"{old} -> {new_key}")


def list_unnamed():
    for key in load_catalog():
        if key.startswith("unnamed_"):
            print(key, files(key)["photo"])


# Camera ----------------------------------------------------------------------------------------


def set_webcam_controls(device, exposure):
    """Fix the webcam's exposure by hand, because its automatic exposure washes out the bright screen.

    The controls are those of the Sonix USB 2.0 camera; other webcams may need other values. A webcam
    that is opened right after its controls changed can stall, so they are only set when they differ,
    followed by a short pause.
    """
    wanted = {"auto_exposure": 1, "exposure_time_absolute": exposure, "backlight_compensation": 0}
    got = subprocess.run(["v4l2-ctl", "-d", device, "--get-ctrl=" + ",".join(wanted)], capture_output=True, text=True)
    current = {}
    for line in got.stdout.splitlines():
        name, _, value = line.partition(":")
        if value.strip().lstrip("-").isdigit():
            current[name.strip()] = int(value)
    if current != wanted:
        subprocess.run(["v4l2-ctl", "-d", device, "-c", ",".join(f"{k}={v}" for k, v in wanted.items())], capture_output=True)
        time.sleep(1.0)


def grab_frame(device, path, attempts=4):
    """Read 15 frames and keep the last one, so the webcam's focus has settled. A stalled read is retried."""
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-f", "v4l2", "-input_format", "mjpeg",
        "-video_size", "1920x1080", "-i", device, "-frames:v", "15", "-update", "1", path,
    ]
    for attempt in range(attempts):
        try:
            subprocess.run(command, check=True, timeout=6, stdin=subprocess.DEVNULL)
            return
        except subprocess.TimeoutExpired:
            time.sleep(0.5)
    raise RuntimeError(f"the webcam {device} does not deliver frames, unplug it and plug it in again")


def take_photo(camera, path, crop=None, exposure=EXPOSURE):
    if camera.startswith("/dev/"):
        set_webcam_controls(camera, exposure)
        grab_frame(camera, path)
    else:
        import requests

        resp = requests.get(camera, timeout=5)
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(resp.content)
    if crop:
        from PIL import Image

        x, y, w, h = crop
        Image.open(path).crop((x, y, x + w, y + h)).save(path)


def env_value(name):
    """A variable from the environment, or else from ENV_FILE. Only the line for that name is read."""
    if os.environ.get(name):
        return os.environ[name]
    if os.path.exists(ENV_FILE):
        pattern = r"""^\s*(?:export\s+)?""" + re.escape(name) + r"""\s*=\s*(["']?)(.*?)\1\s*$"""
        with open(ENV_FILE) as f:
            for line in f:
                match = re.match(pattern, line)
                if match:
                    return match.group(2)
    return None


def read_screen(path, model=VISION_MODEL):
    """Read the screen photo with Claude and return {"slot", "name", "tone", "effect", "level", "other"}.

    Tesseract cannot read this small bitmap font, so the photo is sent to the Anthropic API.
    """
    import anthropic

    key = env_value("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError(f"no ANTHROPIC_API_KEY in the environment or in {ENV_FILE}")
    # A key that is not tied to a workspace needs the workspace named in a header.
    workspace = env_value("ANTHROPIC_WORKSPACE_ID")
    headers = {"anthropic-workspace-id": workspace} if workspace else None
    import io

    from PIL import Image

    def encode(image):
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "JPEG", quality=92)
        return base64.standard_b64encode(buffer.getvalue()).decode()

    screen = Image.open(path)
    # The title row is the hardest part to read, so it is also sent enlarged.
    w, h = screen.size
    title = screen.crop((int(0.12 * w), int(0.25 * h), int(0.80 * w), int(0.47 * h)))
    title = title.resize((title.width * 4, title.height * 4), Image.LANCZOS)
    images = [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encode(screen)}},
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": encode(title)}},
    ]
    # Reading a few words does not need deep thinking; Haiku does not take an effort setting.
    extra = {} if "haiku" in model else {"output_config": {"effort": os.environ.get("VR09_VISION_EFFORT", "low")}}
    response = anthropic.Anthropic(api_key=key, default_headers=headers).messages.create(
        model=model,
        max_tokens=2000,
        **extra,
        messages=[
            {
                "role": "user",
                "content": [
                    *images,
                    {"type": "text", "text": SCREEN_PROMPT},
                ],
            }
        ],
    )
    text = next((b.text for b in response.content if b.type == "text"), "")
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError(f"no JSON in the reply: {text[:80]!r}")
    reading = json.loads(text[start : end + 1])
    print(f"screen read by {model} ({response.usage.input_tokens} tokens in, {response.usage.output_tokens} out)")
    return {k: str(reading.get(k, "")).strip() for k in ("slot", "name", "tone", "effect", "level", "other")}


def photo(camera, crop, exposure=EXPOSURE):
    os.makedirs(PHOTOS, exist_ok=True)
    path = os.path.join(PHOTOS, "test.jpg")
    take_photo(camera, path, crop, exposure)
    print(f"saved {path}")
    try:
        print("screen reads:", read_screen(path))
    except Exception as e:
        print(f"could not read the screen ({e})", file=sys.stderr)


# Audio preview ---------------------------------------------------------------------------------


def find_input(device):
    """Resolve a device given as a number or part of a name to a PortAudio input index."""
    import sounddevice as sd

    if device is None:
        return None
    if device.isdigit():
        return int(device)
    matches = [
        (d["max_input_channels"], -i, i)
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0 and device.lower() in d["name"].lower()
    ]
    if not matches:
        sys.exit(f"no audio input matches {device!r}, see: collect_library.py devices")
    # An interface appears once as a whole and again per port; the whole one has the most inputs.
    return max(matches)[2]


def list_inputs():
    import sounddevice as sd

    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"{i:3d} {d['name']} ({d['max_input_channels']} inputs)")


def parse_style(text, default):
    """Return (label, notes) for a style answer; notes is None for manual playing or skipping."""
    text = (text.strip().lower() or default)
    if text in STYLES:
        return text, STYLES[text]
    if text in ("m", "manual"):
        return "manual", None
    if text in ("s", "skip"):
        return "skip", None
    try:
        notes = [int(n) for n in text.replace(" ", "").split(",")]
    except ValueError:
        return None
    return (text, notes) if notes and all(0 <= n <= 127 for n in notes) else None


def trim_and_fade(audio, rate):
    """Cut the silence at both ends of a recording, keep at most MAX_LENGTH seconds, fade the end out.

    Returns (clip, seconds of silence cut at the start), or None when nothing was heard.
    """
    import numpy as np

    window = int(0.02 * rate)
    skip = int(SKIP * rate)
    signal = audio if audio.ndim == 1 else np.sqrt((audio**2).mean(axis=1))
    usable = signal[skip:]
    count = len(usable) // window
    levels = np.sqrt((usable[: count * window].reshape(count, window) ** 2).mean(axis=1))
    loud = np.nonzero(20 * np.log10(np.maximum(levels, 1e-9)) > SOUND_DB)[0]
    if len(loud) == 0:
        return None
    start = max(0, skip + loud[0] * window - window)
    end = min(skip + (loud[-1] + 1) * window, start + int(MAX_LENGTH * rate), len(audio))
    clip = audio[start:end].copy()
    shape = (-1,) if clip.ndim == 1 else (-1, 1)
    fade_in = min(len(clip), int(FADE_IN * rate))
    fade_out = min(len(clip), int(FADE_OUT * rate))
    clip[:fade_in] *= np.linspace(0.0, 1.0, fade_in).reshape(shape)
    clip[len(clip) - fade_out :] *= np.linspace(1.0, 0.0, fade_out).reshape(shape)
    return clip, start / rate


def record_preview(path, notes, device=None, manual_seconds=4.0):
    """Record the preview of the patch the keyboard is on, playing notes over MIDI unless notes is None."""
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    index = find_input(device)
    info = sd.query_devices(index, "input")
    rate = int(info["default_samplerate"])
    channels = 2 if info["max_input_channels"] >= 2 else 1
    seconds = manual_seconds if notes is None else LEAD_IN + (1.0 if notes == DRUMS else NOTE_LENGTH) + MAX_LENGTH + 0.5
    print(f"recording from {info['name']}" + (", play now" if notes is None else f", playing {notes}"), flush=True)
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=channels, device=index)
    if notes is not None:
        fd = vr09.open_device(vr09.find_port())
        try:
            time.sleep(LEAD_IN)
            if notes == DRUMS:
                for n in DRUM_PATTERN:
                    os.write(fd, bytes([0x90 | DRUM_CHANNEL, n, 100]))
                    time.sleep(0.1)
                    os.write(fd, bytes([0x80 | DRUM_CHANNEL, n, 0]))
                    time.sleep(0.15)
            else:
                for ch in PREVIEW_CHANNELS:
                    for n in notes:
                        os.write(fd, bytes([0x90 | ch, n, PREVIEW_VELOCITY]))
                time.sleep(NOTE_LENGTH)
                for ch in PREVIEW_CHANNELS:
                    for n in notes:
                        os.write(fd, bytes([0x80 | ch, n, 0]))
        finally:
            os.close(fd)
    sd.wait()
    rms = np.sqrt((audio**2).mean(axis=0))
    if channels == 1 or rms.min() < rms.max() / 30:
        # One input is usually silent (a mono cable on a stereo interface): keep the louder one.
        audio = audio[:, int(rms.argmax())]
    peak = 20 * np.log10(max(float(np.abs(audio).max()), 1e-9))
    if peak > -1:
        print(f"warning: the recording peaks at {peak:.1f} dBFS and probably clips, lower the input gain", file=sys.stderr)
    result = trim_and_fade(audio, rate)
    if result is None:
        print(f"warning: no sound heard (peak {peak:.1f} dBFS): check the cable, the gain and the notes", file=sys.stderr)
        return False
    clip, cut = result
    sf.write(path, clip, rate)
    print(f"saved {len(clip) / rate:.2f}s preview, peak {peak:.1f} dBFS, {cut:.2f}s of silence cut at the start")
    return True


def ask_style(default):
    while True:
        answer = ask(f"Preview [Enter = {default}] chord, pad, bass, lead, m = you play, s = skip, or notes like 48,55: ")
        parsed = parse_style(answer, default)
        if parsed:
            return parsed
        print("not understood")


def preview_again(key, style_text, device):
    patches = load_catalog()
    if key not in patches:
        sys.exit(f"no patch named {key!r} in {CATALOG}")
    parsed = parse_style(style_text or patches[key].get("preview", "chord"), "chord")
    if not parsed or parsed[0] == "skip":
        sys.exit("give a style: chord, pad, bass, lead, m or notes like 48,55")
    label, notes = parsed
    os.makedirs(AUDIO, exist_ok=True)
    if record_preview(files(key)["audio"], notes, device):
        patches[key]["preview"] = label
        save_catalog(patches)


def reread(everything, model=VISION_MODEL):
    """Read the saved photos again and refresh tone, effect, level and other. Titles are never changed."""
    patches = load_catalog()
    done = 0
    for key, entry in patches.items():
        if entry.get("reviewed") and not everything:
            continue
        photo_path = files(key)["photo"]
        if not os.path.exists(photo_path):
            continue
        try:
            reading = read_screen(photo_path, model)
        except Exception as e:
            print(f"{key}: not read ({e})", file=sys.stderr)
            continue
        entry.update({k: reading.get(k, "") for k in ("tone", "effect", "level", "other")})
        entry["screen_slot"] = reading.get("slot", "")
        done += 1
        if done % 10 == 0:
            save_catalog(patches)
    save_catalog(patches)
    print(f"{done} patches read again")


def read_setlist(path):
    """The dump names in a setlist file: one per line, whatever follows a # is a comment."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return [name for name in (line.split("#", 1)[0].strip() for line in f) if name]


def write_setlist(path, keys, patches=None):
    """Write a setlist file: one key per line, with the title and tone after a # as a reminder."""
    patches = load_catalog() if patches is None else patches
    lines = ["# One dump name per line, in performance order. Blank lines and # comments are ignored.",
             "# The text after # is only a reminder. This file is also written by the web page (npm start in web/).", ""]
    for key in keys:
        e = patches.get(key)
        lines.append(f"{key}    # {e['title']}  |  {e.get('tone', '')}" if e else key)
    temporary = path + ".tmp"
    with open(temporary, "w") as out:
        out.write("\n".join(lines) + "\n")
    os.replace(temporary, path)


def make_setlist(path):
    """Write a setlist file with every patch in bank and slot order, for pedal_scenes.py."""
    patches = load_catalog()
    write_setlist(path, [k for k, _ in sorted(patches.items(), key=lambda kv: kv[1]["captured"])], patches)
    print(f"wrote {path} with {len(patches)} patches")


def serve(options):
    """Start the library web page: an Astro app in web/, with the catalog and the setlist as its data."""
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
    if not os.path.isdir(os.path.join(web, "node_modules")):
        sys.exit(f"install the page's packages once: cd {web} && npm install")
    env = dict(os.environ)
    env.setdefault("VR09_ROOT", os.getcwd())
    if "--setlist" in options:
        env["VR09_SETLIST"] = os.path.abspath(options[options.index("--setlist") + 1])
    extra = ["--port", options[options.index("--port") + 1]] if "--port" in options else []
    script = "dev" if "--no-browser" in options else "start"  # start opens the browser
    command = ["npm", "run", script, "--prefix", web] + (["--"] + extra if extra else [])
    try:
        sys.exit(subprocess.run(command, env=env).returncode)
    except KeyboardInterrupt:
        sys.exit(0)


def unique_key(key, patches):
    """Add _2, _3... when a patch with this key was captured already."""
    candidate, n = key, 1
    while candidate in patches or os.path.exists(files(candidate)["dump"]):
        n += 1
        candidate = f"{key}_{n}"
    return candidate


def sync():
    """After editing titles in the catalog, rename the files and keys to match them."""
    for key, entry in list(load_catalog().items()):
        title = entry.get("title", "")
        if title and safe(title) != key:
            try:
                rename(key, title)
            except SystemExit as e:
                print(f"skipped {key}: {e}", file=sys.stderr)


# Capture loop ----------------------------------------------------------------------------------


def capture_one(patches, label, camera, use_camera, crop, use_audio, audio_device, exposure, default_style, auto, use_vision, vision_model):
    """Capture the patch the keyboard is on, as the slot called label (such as 4-2). Returns False to stop.

    The bank and slot come from the caller's count, not from the screen: the small font makes the model
    misread the digits. Only the name, tone and effect are read from the screen.

    Whatever fails, the files of this patch are removed again, so the library never holds a half patch.
    """
    reading = {}
    tmp_photo = os.path.join(PHOTOS, "_tmp.jpg") if use_camera else None
    created = []
    try:
        if use_camera:
            try:
                take_photo(camera, tmp_photo, crop, exposure)
                if use_vision:
                    reading = read_screen(tmp_photo, vision_model)
            except Exception as e:
                print(f"camera or screen reading failed ({e})", file=sys.stderr)
                if not os.path.exists(tmp_photo):
                    tmp_photo = None

        if reading.get("slot") and reading["slot"] != label:
            print(f"note: the screen was read as {reading['slot']} but this is {label}; keeping {label}")
        guess = " ".join(part for part in (label, reading.get("name")) if part)
        if auto:
            name = guess
        else:
            answer = ask(f"Name [{guess or 'none read'}]: Enter to accept, type to replace, q to stop: ").strip()
            if answer.lower() == "q":
                return False
            name = answer or guess
        key = unique_key(safe(name) if name else "unnamed_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S"), patches)

        # The dump comes first: it is the part that matters, and the patch is dropped if it fails.
        print("reading the dump over MIDI...")
        created.append(files(key)["dump"])
        vr09.dump(key)

        style = "skip"
        if use_audio:
            if "kit" in reading.get("tone", "").lower() and default_style == "chord":
                default_style = "drums"  # a drum kit makes no sound on the parts the chord is sent to
            style, notes = parse_style(default_style, "chord") if auto else ask_style(default_style)
            if style != "skip":
                created.append(files(key)["audio"])
                try:
                    record_preview(files(key)["audio"], notes, audio_device)
                except Exception as e:
                    print(f"audio recording failed ({e}), continuing without a preview", file=sys.stderr)
        if tmp_photo and os.path.exists(tmp_photo):
            created.append(files(key)["photo"])
            os.replace(tmp_photo, files(key)["photo"])

        patches[key] = {
            "title": name,
            "captured": datetime.datetime.now().isoformat(timespec="seconds"),
            "preview": style,
            "tags": [],
            "notes": "",
            "tone": reading.get("tone", ""),
            "effect": reading.get("effect", ""),
            "level": reading.get("level", ""),
            "other": reading.get("other", ""),
            "screen_slot": reading.get("slot", ""),
            "reviewed": not (bool(guess) and name == guess) and bool(name),
        }
        save_catalog(patches)
        print(f"saved as {key}" + (f" ('{name}')" if name else ", name it later with: rename"))
        return True
    except BaseException:
        for path in created:
            if os.path.exists(path):
                os.remove(path)
        raise
    finally:
        if tmp_photo and os.path.exists(tmp_photo):
            os.remove(tmp_photo)


def parse_slot(text):
    """Read a label such as 4-2 into (bank, slot), or None."""
    match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", text)
    return (int(match.group(1)), int(match.group(2))) if match else None


def next_slot(bank, slot, per_bank):
    return (bank, slot + 1) if slot < per_bank else (bank + 1, 1)


def derive_start(patches, per_bank):
    """The slot after the most recently captured one, or 1-1 for an empty library."""
    if not patches:
        return 1, 1
    latest = max(patches.values(), key=lambda e: e["captured"])
    match = re.match(r"\s*(\d+\s*-\s*\d+)", latest["title"])
    found = parse_slot(match.group(1)) if match else None
    return next_slot(*found, per_bank) if found else (1, 1)


def capture(camera, use_camera, crop, use_audio, audio_device, exposure, default_style, auto=False, use_vision=True, vision_model=VISION_MODEL, start=None, per_bank=4):
    os.makedirs(PHOTOS, exist_ok=True)
    os.makedirs(AUDIO, exist_ok=True)
    patches = load_catalog()
    bank, slot = parse_slot(start) if start else derive_start(patches, per_bank)
    print(f"starting at {bank}-{slot}, {per_bank} patches per bank (change it with --start BANK-SLOT or by typing a slot below)")
    try:
        while True:
            answer = ask(f"\nRecall {bank}-{slot} on the keyboard panel, then press Enter (or type a slot such as 2-3, q to stop): ")
            if answer.strip().lower() == "q":
                break
            jump = parse_slot(answer)
            if jump:
                bank, slot = jump
            elif answer.strip():
                print("not understood: press Enter, type a slot like 2-3, or q")
                continue
            try:
                if not capture_one(patches, f"{bank}-{slot}", camera, use_camera, crop, use_audio, audio_device, exposure, default_style, auto, use_vision, vision_model):
                    break
                bank, slot = next_slot(bank, slot, per_bank)
            except (Exception, SystemExit) as e:
                # One bad patch must not end the session: say what failed and ask for the same slot again.
                print(f"patch skipped, nothing was saved for it: {e}", file=sys.stderr)
    except KeyboardInterrupt:
        print("\nstopped, the patches saved so far are in the catalog")


def parse_crop(text):
    parts = [int(v) for v in text.split(",")]
    if len(parts) != 4:
        sys.exit("--crop takes X,Y,W,H in pixels")
    return tuple(parts)


if __name__ == "__main__":
    args = sys.argv[1:]
    command = args[0] if args else ""
    if command == "devices":
        list_inputs()
    elif command == "unnamed":
        list_unnamed()
    elif command == "sync":
        sync()
    elif command in ("serve", "review"):
        serve(args[1:])
    elif command == "setlist":
        make_setlist(args[1] if len(args) > 1 else "setlist.txt")
    elif command == "reread":
        reread("--all" in args, args[args.index("--vision-model") + 1] if "--vision-model" in args else VISION_MODEL)
    elif command == "rename" and len(args) == 3:
        rename(args[1], args[2])
    elif command == "preview" and len(args) >= 2:
        rest, device = args[2:], os.environ.get("VR09_AUDIO_DEVICE")
        if "--audio-device" in rest:
            at = rest.index("--audio-device")
            device = rest[at + 1]
            rest = rest[:at] + rest[at + 2 :]
        preview_again(args[1], rest[0] if rest else None, device)
    elif command in ("capture", "photo"):
        camera, crop, exposure = DEFAULT_CAM, None, EXPOSURE
        use_camera, use_audio, default_style, auto = True, True, "chord", False
        use_vision, vision_model = True, VISION_MODEL
        start, per_bank = None, 4
        audio_device = os.environ.get("VR09_AUDIO_DEVICE")
        i = 1
        while i < len(args):
            option = args[i]
            if option == "--cam":
                camera, i = args[i + 1], i + 2
            elif option == "--crop":
                crop, i = parse_crop(args[i + 1]), i + 2
            elif option == "--exposure":
                exposure, i = int(args[i + 1]), i + 2
            elif option == "--no-camera" and command == "capture":
                use_camera, i = False, i + 1
            elif option == "--no-audio" and command == "capture":
                use_audio, i = False, i + 1
            elif option == "--audio-device" and command == "capture":
                audio_device, i = args[i + 1], i + 2
            elif option == "--style" and command == "capture":
                default_style, i = args[i + 1], i + 2
            elif option == "--auto" and command == "capture":
                auto, i = True, i + 1
            elif option == "--start" and command == "capture":
                start, i = args[i + 1], i + 2
                if not parse_slot(start):
                    sys.exit("--start takes BANK-SLOT, such as 5-1")
            elif option == "--per-bank" and command == "capture":
                per_bank, i = int(args[i + 1]), i + 2
            elif option == "--no-vision" and command == "capture":
                use_vision, i = False, i + 1
            elif option == "--vision-model" and command == "capture":
                vision_model, i = args[i + 1], i + 2
            else:
                sys.exit(f"unknown argument: {option}")
        if command == "photo":
            photo(camera, crop, exposure)
        else:
            if not parse_style(default_style, "chord"):
                sys.exit(f"unknown style {default_style!r}")
            capture(camera, use_camera, crop, use_audio, audio_device, exposure, default_style, auto, use_vision, vision_model, start, per_bank)
    else:
        sys.exit(__doc__)
