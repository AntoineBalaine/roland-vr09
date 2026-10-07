"""Extract the VR-09 tone list (pages 15 to 18 of the MIDI implementation) into a JSON file."""
import json, re, subprocess

PDF = "docs/VR-09_VR-730_MIDI_Implementation.pdf"
ENTRY = re.compile(r"^\s*(?P<name>.+?)\s+(?:(?P<star>\*\d)\s+)?(?P<pc>\d+) \((?P<hex>[0-9A-F]{2})h\)\s+(?P<msb>\d+) \([0-9A-F]{2}h\)\s+(?P<lsb>\d+) \([0-9A-F]{2}h\)\s*$")
HEADER = re.compile(r"^\s*\[(?P<group>[A-Z0-9. \-]+)\]\s*$")
SECTION = re.compile(r"●\s*(Piano|Synthesizer|Drum) Section")

def column(page, x, w):
    out = subprocess.run(["pdftotext", "-f", str(page), "-l", str(page), "-x", str(x), "-y", "0", "-W", str(w), "-H", "842", "-layout", PDF, "-"],
                         capture_output=True, text=True).stdout
    return out.splitlines()

tones, section, group, notes = [], None, None, set()
for page in (15, 16, 17, 18):
    for x, w in ((0, 300), (300, 296)):
        for line in column(page, x, w):
            if m := SECTION.search(line):
                section = {"Piano": "piano", "Synthesizer": "synth", "Drum": "drum"}[m.group(1)]; group = None; continue
            if m := HEADER.match(line):
                group = m.group("group").strip(); continue
            if m := ENTRY.match(line):
                tones.append({"section": section, "group": group, "name": m.group("name").strip(), "note": m.group("star"),
                              "tone_number": int(m.group("hex"), 16), "bank_msb": int(m.group("msb")), "bank_lsb": int(m.group("lsb")),
                              "program_number": int(m.group("pc"))})
json.dump(tones, open("docs/tones.json", "w"), indent=1)
import collections
print(len(tones), "tones;", dict(collections.Counter(t["section"] for t in tones)))
print("without section:", sum(1 for t in tones if t["section"] is None), "without group:", sum(1 for t in tones if t["group"] is None))
print("consistency (program number = tone number + 1):", all(t["program_number"] == t["tone_number"] + 1 for t in tones))
print(collections.Counter((t["section"], t["group"]) for t in tones))
