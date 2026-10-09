#!/usr/bin/env python3
"""Interactively build a library of VR-09 patches: a dump, a name (OCR'd off the LED screen, or
typed), and a short audio preview, one patch at a time.

  collect_library.py capture                 run the interactive loop
  collect_library.py capture --cam URL        override the camera snapshot URL for this run
  collect_library.py capture --no-camera      skip the photo/OCR step, type the name instead
  collect_library.py capture --duration N     seconds of audio to record per preview (default 8)

Each captured patch writes:
  dumps/<name>.json        parameter dump, same format as vr09.py dump
  library/photos/<name>.jpg  the LED screen photo (if a camera was used)
  library/audio/<name>.wav   the audio preview
  library/catalog.json       one row per patch: name, ocr text, timestamp

Dependencies beyond the standard library: requests (camera snapshot), pytesseract + the
tesseract-ocr system package (OCR), sounddevice + soundfile (audio recording). Each is only
imported when the feature that needs it is used, so e.g. --no-camera works without pytesseract.

Camera: any Android IP-camera app that serves a JPEG snapshot over HTTP works (the common "IP
Webcam" app's default snapshot URL is http://<phone-ip>:8080/shot.jpg). Set VR09_CAM_URL or pass
--cam if that default is wrong for your setup.
"""
import datetime
import json
import os
import sys

import vr09

LIBRARY = "library"
PHOTOS = os.path.join(LIBRARY, "photos")
AUDIO = os.path.join(LIBRARY, "audio")
CATALOG = os.path.join(LIBRARY, "catalog.json")
DEFAULT_CAM_URL = os.environ.get("VR09_CAM_URL", "http://192.168.1.50:8080/shot.jpg")


def ask(prompt):
    try:
        return input(prompt)
    except EOFError:
        return ""


def take_photo(cam_url, path):
    import requests

    resp = requests.get(cam_url, timeout=5)
    resp.raise_for_status()
    with open(path, "wb") as f:
        f.write(resp.content)


def ocr(path):
    import pytesseract
    from PIL import Image

    return pytesseract.image_to_string(Image.open(path)).strip()


def record_audio(path, duration, samplerate=44100):
    import sounddevice as sd
    import soundfile as sf

    print(f"recording {duration}s, play now", flush=True)
    audio = sd.rec(int(duration * samplerate), samplerate=samplerate, channels=1)
    sd.wait()
    sf.write(path, audio, samplerate)


def load_catalog():
    if os.path.exists(CATALOG):
        with open(CATALOG) as f:
            return json.load(f)
    return []


def save_catalog(entries):
    os.makedirs(LIBRARY, exist_ok=True)
    with open(CATALOG, "w") as f:
        json.dump(entries, f, indent=2)


def capture(cam_url, use_camera, duration):
    os.makedirs(PHOTOS, exist_ok=True)
    os.makedirs(AUDIO, exist_ok=True)
    catalog = load_catalog()

    while True:
        ask("\nRecall the next patch on the keyboard panel, then press Enter (blank name to stop): ")

        ocr_text = ""
        photo_path = None
        if use_camera:
            photo_path = os.path.join(PHOTOS, "_tmp.jpg")
            try:
                take_photo(cam_url, photo_path)
                ocr_text = ocr(photo_path)
                print(f"OCR read: {ocr_text!r}")
            except Exception as e:
                print(f"camera/OCR failed ({e}), type the name instead", file=sys.stderr)

        name = ask(f"Name [{ocr_text or 'required'}]: ").strip() or ocr_text.strip()
        if not name:
            print("no name given, stopping")
            break
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)

        ask("Press Enter, then play a few notes for the audio preview: ")
        audio_path = os.path.join(AUDIO, f"{safe_name}.wav")
        try:
            record_audio(audio_path, duration)
        except Exception as e:
            print(f"audio recording failed ({e}), continuing without a preview", file=sys.stderr)
            audio_path = None

        if photo_path:
            final_photo = os.path.join(PHOTOS, f"{safe_name}.jpg")
            os.replace(photo_path, final_photo)
            photo_path = final_photo

        print("reading the dump over MIDI...")
        vr09.dump(safe_name)

        catalog = [e for e in catalog if e["name"] != safe_name]
        catalog.append(
            {
                "name": safe_name,
                "display_name": name,
                "ocr_text": ocr_text,
                "photo": photo_path,
                "audio": audio_path,
                "dump": f"dumps/{safe_name}.json",
                "captured_at": datetime.datetime.now().isoformat(timespec="seconds"),
            }
        )
        save_catalog(catalog)
        print(f"saved '{name}' as {safe_name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] != "capture":
        sys.exit(__doc__)
    cam_url = DEFAULT_CAM_URL
    use_camera = True
    duration = 8
    i = 1
    while i < len(args):
        if args[i] == "--cam":
            cam_url = args[i + 1]
            i += 2
        elif args[i] == "--no-camera":
            use_camera = False
            i += 1
        elif args[i] == "--duration":
            duration = float(args[i + 1])
            i += 2
        else:
            sys.exit(f"unknown argument: {args[i]}")
    capture(cam_url, use_camera, duration)
