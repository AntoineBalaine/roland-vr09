# Integrating VR-09 patches into Pot Browser

Goal: make a captured VR-09 patch (from `collect_library.py`, see the repo root) show up as a
double-clickable library entry in the user's Pot Browser fork at `/tank/projects/potbrowser`
(Helgobox), the same way a VST preset does, with double-click sending the patch to the keyboard
over MIDI instead of loading plugin state.

Not started yet. This is a reference for picking the work back up, from a read-only research
pass over the potbrowser codebase (no potbrowser files were changed).

## What potbrowser already has

Rust workspace, REAPER plugin, browser UI in `egui` (crate `pot-browser`). Modular, one crate per
concern (`pot`, `pot-db`, `pot-api`, persistence types in `helgobox_api::persistence`).

- **Generic preset struct**, `pot/src/lib.rs:1346-1468`: `PotPreset { common: PotPresetCommon,
  kind: PotPresetKind }`. `PotPresetCommon` holds name, a persistent ID, plugin/product IDs
  (metadata hints, not required), and metadata (author, vendor, comment, file size, mod date).
  `PotPresetKind` is an enum: `FileBased`, `ProjectBased`, `Internal`, `DefaultFactory`. Nothing
  about the struct assumes a VST origin.
- **Pluggable preset sources**, `pot/src/provider_database.rs`: a `Database` trait (`refresh`,
  `query_filter_collections`, `query_presets`, `find_preset_by_id`) operating on `PotPreset`.
  Concrete providers in `pot/src/providers/`: `komplete.rs`, `directory.rs`, `ini.rs`,
  `projects.rs`, `defaults.rs`. No hardware-backed provider exists yet, but the trait itself has
  no VST-specific requirement.
- **Double-click load path**: `pot-browser/src/pot_browser_panel.rs:2050`
  (`button.double_clicked()`) → `load_preset_and_regain_focus` (`pot_browser_panel.rs:3335`) →
  queues `ReaperCommand::LoadPreset { preset, options, os_window }`
  (`reaper_commands.rs:17`) → `execute_reaper_command` (`reaper_commands.rs:61`) → 
  `pot_unit.load_preset(&preset, options)` (`pot/src/lib.rs:747`) →
  `load_file_based_preset` (`lib.rs:838-870`), which branches on file extension /
  `PotPresetKind` (e.g. `.nksf` → `load_nks_preset` → `fx.set_vst_chunk(...)`). One centralized
  match, not a trait object, but already structured per-kind.
- **Audio previews**: already first-class (`pot/src/lib.rs:2034-2089`). Either the preset's own
  audio file, a recorded preview under the REAPER resource dir keyed by a content hash
  (`preview_recorder::get_preview_file_path_from_hash`), or a database-specific preview path
  (`db_specific_preview_file`). Tracked via a small SQLite-backed registry (`pot/src/db.rs`,
  see `POT_DB_DESIGN.md`).

## The shape of the work, when it's time

1. **New `PotPresetKind` variant**, something like `HardwarePatch { dump_path: Utf8PathBuf }` (or
   a reference to a catalog entry from `collect_library.py`'s `library/catalog.json`).
2. **New provider**, `pot/src/providers/vr09.rs` (or similar), implementing `Database`: reads
   `library/catalog.json` and `dumps/*.json`, exposes one `PotPreset` per captured patch, with
   `name` from the catalog's `display_name` and the audio preview pointed at
   `library/audio/<name>.wav`.
3. **New load handler** in the `load_file_based_preset` (or sibling) match arm for
   `HardwarePatch`: instead of `fx.set_vst_chunk(...)`, call out to the recall logic already in
   `vr09.py` (`write_differences` / `recall`), ported to Rust or shelled out to, sending the
   dump's values to the keyboard over the same USB MIDI connection documented in
   `midi-capabilities.md`.
4. **Reuse the existing preview mechanism** as-is for playback — no new preview plumbing needed,
   just point `db_specific_preview_file` (or equivalent) at the `.wav` captured alongside the
   dump.

## Open questions for later

- Whether the recall should go through a shelled-out call to `vr09.py recall NAME`, or whether
  the DT1 write logic (`groups`, `varying_keys`, `write_differences` in `vr09.py`) should be
  ported into Rust so potbrowser doesn't depend on a Python subprocess and a live USB device at
  load time.
- How `varying_keys` (the "switch set" computed across saved dumps) should be recomputed as the
  catalog grows — today it's computed from whatever is in `dumps/` at call time.
- Whether `PotPreset.common.plugin_ids`/`product_ids` should be left empty for hardware patches,
  or given a synthetic identifier so filtering/search UI doesn't special-case an empty vendor.

## Related

- `collect_library.py` — captures the dump, photo/OCR name, and audio preview per patch.
- `docs/midi-capabilities.md` — the recall mechanism (`vr09.py recall`) this would call into.
- `docs/cc-modulation-table.md` — unrelated to this integration, kept separate.
