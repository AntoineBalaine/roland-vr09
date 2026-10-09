#!/usr/bin/env python3
"""Correct the bank (and optionally the slot) of captured patches whose screen reading was wrong.

  fix_banks.py                       show what would change (nothing is modified)
  fix_banks.py --apply               change the bank digit in the titles, rename keys and files, keep a backup
  fix_banks.py --apply --renumber-slots
                                     also set the slot from the capture order (1 to 4 in each group)

Run it when no capture is running: the capture loop keeps the catalog in memory and rewrites the whole
file after each patch, so an edit made meanwhile would be overwritten and the renamed files would no
longer match it. Patches are named by key, so patches captured later are left alone.

BANKS lists, for each bank, the keys of its patches in the order they were captured. A bank holds four
patches, so the position in the list is the slot the patch should have.
"""
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import collect_library as cl

BANKS = {
    "1": ["1-1_MassiveOrgDF", "1-2_JazzRoll_OF", "1-4_FatterPno_DF", "1-1_BottomPno_0F"],
    "2": ["2-1_Piano_Org", "2-2_Ueuo_Piano", "2-1_Organ_EP", "2-01_LocaL0ra0F"],
}

# Patches captured twice: {duplicate: the patch kept}. A duplicate is removed, with its files, only when
# its dump is identical to the one of the patch kept.
DUPLICATES = {"1-1_PatterPno_UF": "1-4_FatterPno_DF"}


def capture_running():
    """True when a Python process is running collect_library.py capture.

    The arguments of each process are examined, because matching text on the command line also matches
    a shell or editor whose command merely mentions it.
    """
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == os.getpid():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as f:
                argv = [a.decode(errors="replace") for a in f.read().split(b"\0") if a]
        except OSError:
            continue
        if (
            len(argv) >= 3
            and os.path.basename(argv[0]).startswith("python")
            and any(os.path.basename(a) == "collect_library.py" for a in argv[1:])
            and "capture" in argv
        ):
            return True
    return False


def new_title(title, bank, slot, renumber):
    if renumber:
        return re.sub(r"^\d+-\d+", f"{bank}-{slot}", title)
    return re.sub(r"^\d+-", f"{bank}-", title)


def main():
    apply = "--apply" in sys.argv[1:]
    renumber = "--renumber-slots" in sys.argv[1:]
    patches = cl.load_catalog()
    plan, removals = [], []
    for duplicate, kept in DUPLICATES.items():
        if duplicate not in patches:
            print(f"{duplicate}: not in the catalog, skipped (already removed?)")
        elif kept not in patches:
            print(f"{duplicate}: the patch to keep, {kept}, is not in the catalog, skipped")
        elif open(cl.files(duplicate)["dump"]).read() != open(cl.files(kept)["dump"]).read():
            print(f"{duplicate}: its dump differs from {kept}, so it is NOT removed")
        else:
            removals.append(duplicate)
            print(f"{duplicate}: identical to {kept}, removed with its files")
    for bank, keys in BANKS.items():
        for slot, key in enumerate(keys, 1):
            if key not in patches:
                print(f"{key}: not in the catalog, skipped (already renamed?)")
                continue
            old = patches[key]["title"]
            new = new_title(old, bank, slot, renumber)
            suggestion = new_title(old, bank, slot, True)
            if new == old:
                print(f"{key}: title {old!r} is already right, skipped")
                continue
            plan.append((key, old, new))
            note = "" if renumber or suggestion == new else f"   (with --renumber-slots: {suggestion!r})"
            print(f"{key}: {old!r} -> {new!r}{note}")
    if not plan and not removals:
        print("nothing to do")
        return
    if not apply:
        print("\nDry run. Run again with --apply to make these changes.")
        return
    if capture_running():
        sys.exit("a capture is running: stop it with q, then run this again")

    shutil.copy(cl.CATALOG, cl.CATALOG + ".bak")
    print(f"\nbackup of the catalog: {cl.CATALOG}.bak")
    for key in removals:
        for path in cl.files(key).values():
            if os.path.exists(path):
                os.remove(path)
        del patches[key]
    for key, old, new in plan:
        patches[key]["title"] = new
    cl.save_catalog(patches)
    cl.sync()  # renames the keys and files to match the new titles
    print("done")


if __name__ == "__main__":
    main()
