#!/usr/bin/env python3
"""Interactively build a library of VR-09 patches: a dump, a photo of the screen, and a short audio
preview that the tool plays itself over MIDI, one patch at a time.

  collect_library.py capture [options]        run the interactive loop
  collect_library.py preview NAME [STYLE]     record the audio preview of a patch again (the keyboard
                                              must be on that patch)
  collect_library.py photo [--cam SOURCE] [--crop X,Y,W,H] [--exposure N]
                                              take one photo into library/photos/test.jpg and print
                                              what the OCR reads, to set up the camera
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
  --no-audio           skip the audio preview

Preview styles. The tool sends the notes to the pedal, lower and upper parts (MIDI channels 2, 3 and 4 in
Mode 2) for half a second, records until the tail has died, cuts the silence at both ends, keeps at
most 2 seconds and fades the end out. Only the parts the patch uses make a sound.
  chord   C major triad around middle C         pad     wide C major chord from C3
  bass    one low C (C2)                        lead    one G4
  m       you play on the keyboard (4 s recording)
  48,55   any MIDI note numbers, separated by commas
  s       skip the preview

Each captured patch writes:
  dumps/<key>.json          parameter dump, same format as vr09.py dump
  library/photos/<key>.jpg  the screen photo (if a camera was used)
  library/audio/<key>.wav   the audio preview
  library/catalog.yaml      one entry per patch, meant to be edited by hand; the three files above are
                            found from the entry's key, so rename entries with the rename command

Dependencies beyond the standard library, installed in .venv: pyyaml, numpy, sounddevice, soundfile,
requests (phone camera), pillow and pytesseract (OCR, with the tesseract-data-eng system package).
Each is only imported when the feature that needs it is used.

Camera: a webcam is the simplest. It is read with ffmpeg (a system package, no Python module), so
--cam /dev/video0 is all it takes; the default is /dev/video0 when that device exists. Otherwise any
Android IP-camera app that serves a JPEG snapshot over HTTP works (the common "IP Webcam" app's
default snapshot URL is http://<phone-ip>:8080/shot.jpg). Set VR09_CAM or pass --cam to choose.
"""
import datetime
import json
import os
import subprocess
import sys
import time

import vr09

EXPOSURE = int(os.environ.get("VR09_EXPOSURE", "40"))
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
STYLES = {"chord": [60, 64, 67], "pad": [48, 55, 64, 67], "bass": [36], "lead": [67]}
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
    with open(CATALOG, "w") as f:
        f.write(
            "# Patch library, written by collect_library.py. Edit title, tags and notes freely.\n"
            "# The key of an entry is the stem of its files: dumps/<key>.json, library/photos/<key>.jpg and\n"
            "# library/audio/<key>.wav. To rename an entry, use: collect_library.py rename OLD NEW\n"
        )
        yaml.safe_dump({"patches": patches}, f, sort_keys=False, allow_unicode=True, default_flow_style=False, width=100)


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


def ocr(path):
    """A hint only: this screen font is too small for Tesseract to read reliably."""
    import pytesseract
    from PIL import Image, ImageOps, ImageStat

    image = ImageOps.grayscale(Image.open(path))
    image = image.resize((image.width * 3, image.height * 3))
    if ImageStat.Stat(image).mean[0] < 110:
        image = ImageOps.invert(image)
    return pytesseract.image_to_string(image, config="--psm 6").strip()


def photo(camera, crop, exposure=EXPOSURE):
    os.makedirs(PHOTOS, exist_ok=True)
    path = os.path.join(PHOTOS, "test.jpg")
    take_photo(camera, path, crop, exposure)
    print(f"saved {path}")
    try:
        print(f"OCR read: {ocr(path)!r}")
    except Exception as e:
        print(f"OCR failed ({e})", file=sys.stderr)


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
    seconds = manual_seconds if notes is None else LEAD_IN + NOTE_LENGTH + MAX_LENGTH + 0.5
    print(f"recording from {info['name']}" + (", play now" if notes is None else f", playing {notes}"), flush=True)
    audio = sd.rec(int(seconds * rate), samplerate=rate, channels=channels, device=index)
    if notes is not None:
        fd = vr09.open_device(vr09.find_port())
        try:
            time.sleep(LEAD_IN)
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


# Capture loop ----------------------------------------------------------------------------------


def capture(camera, use_camera, crop, use_audio, audio_device, exposure, default_style):
    os.makedirs(PHOTOS, exist_ok=True)
    os.makedirs(AUDIO, exist_ok=True)
    patches = load_catalog()

    while True:
        ask("\nRecall the next patch on the keyboard panel, then press Enter: ")

        ocr_text = ""
        tmp_photo = None
        if use_camera:
            tmp_photo = os.path.join(PHOTOS, "_tmp.jpg")
            try:
                take_photo(camera, tmp_photo, crop, exposure)
                ocr_text = ocr(tmp_photo)
            except Exception as e:
                print(f"camera/OCR failed ({e})", file=sys.stderr)
                if not os.path.exists(tmp_photo):
                    tmp_photo = None

        hint = f" (OCR guess: {ocr_text!r})" if ocr_text else ""
        name = ask(f"Name{hint}. Enter to name it later from the photo, q to stop: ").strip()
        if name.lower() == "q":
            if tmp_photo and os.path.exists(tmp_photo):
                os.remove(tmp_photo)
            break
        key = safe(name) if name else "unnamed_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

        style = "skip"
        if use_audio:
            style, notes = ask_style(default_style)
            if style != "skip":
                try:
                    record_preview(files(key)["audio"], notes, audio_device)
                except Exception as e:
                    print(f"audio recording failed ({e}), continuing without a preview", file=sys.stderr)

        if tmp_photo:
            os.replace(tmp_photo, files(key)["photo"])

        print("reading the dump over MIDI...")
        vr09.dump(key)

        previous = patches.get(key, {})
        patches[key] = {
            "title": name,
            "captured": datetime.datetime.now().isoformat(timespec="seconds"),
            "preview": style,
            "tags": previous.get("tags", []),
            "notes": previous.get("notes", ""),
            "ocr_hint": ocr_text,
        }
        save_catalog(patches)
        print(f"saved as {key}" + (f" ('{name}')" if name else ", name it later with: rename"))


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
        use_camera, use_audio, default_style = True, True, "chord"
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
            else:
                sys.exit(f"unknown argument: {option}")
        if command == "photo":
            photo(camera, crop, exposure)
        else:
            if not parse_style(default_style, "chord"):
                sys.exit(f"unknown style {default_style!r}")
            capture(camera, use_camera, crop, use_audio, audio_device, exposure, default_style)
    else:
        sys.exit(__doc__)
