// The server side of the library page: reads and writes library/catalog.yaml and the setlist file,
// renames patches' files, and answers the page's requests. Used by the API routes in src/pages.
import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";
import { dt1Message, recallMessages, type Dump } from "./recall";

// VR09_ROOT (default: the folder above web/) holds library/, dumps/ and setlist.txt.
const ROOT = path.resolve(process.env.VR09_ROOT ?? path.join(process.cwd(), ".."));
const LIBRARY = path.join(ROOT, "library");
export const MEDIA = { photos: path.join(LIBRARY, "photos"), audio: path.join(LIBRARY, "audio") } as const;
const DUMPS = path.join(ROOT, "dumps");
const CATALOG = path.join(LIBRARY, "catalog.yaml");
const SETLIST = path.resolve(ROOT, process.env.VR09_SETLIST ?? "setlist.txt");

const EDITABLE = ["title", "tone", "effect", "level", "other", "notes"] as const;
const HEADER =
  "# Patch library, written by collect_library.py. Edit title, tags and notes freely.\n" +
  "# The key of an entry is the stem of its files: dumps/<key>.json, library/photos/<key>.jpg and\n" +
  "# library/audio/<key>.ogg. To rename an entry, use: collect_library.py rename OLD NEW\n";

export interface CatalogEntry {
  title: string;
  captured: string;
  tags?: string[];
  reviewed?: boolean;
  [field: string]: unknown;
}
export type Catalog = Record<string, CatalogEntry>;

export interface PagePatch {
  title: string;
  tone: string;
  effect: string;
  level: string;
  other: string;
  notes: string;
  tags: string[];
  reviewed: boolean;
  touche: string;
  photo: string;
  audio: string;
}
export interface PageData {
  patches: Record<string, PagePatch>;
  order: string[];
  saved: string[];
  capture_running: boolean;
  message?: string;
}

export class HttpError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

// The name of a patch's files: letters, digits, - and _ stay, anything else becomes _ (as in collect_library.py).
export const safe = (name: string): string =>
  Array.from(name)
    .map((c) => (/[\p{L}\p{N}]/u.test(c) || c === "-" || c === "_" ? c : "_"))
    .join("");

const filesOf = (key: string) => ({
  dump: path.join(DUMPS, `${key}.json`),
  photo: path.join(MEDIA.photos, `${key}.jpg`),
  audio: path.join(MEDIA.audio, `${key}.ogg`),
});

// Catalog ---------------------------------------------------------------------------------------

// YAML 1.1 on purpose: Python's yaml (used by collect_library.py) reads the file as 1.1, where unquoted
// yes, no, on, off and timestamps mean something else. Writing as 1.1 quotes exactly those strings.
const YAML_OPTIONS = { version: "1.1" } as const;

function loadCatalog(): Catalog {
  if (!fs.existsSync(CATALOG)) return {};
  const parsed = YAML.parse(fs.readFileSync(CATALOG, "utf8"), YAML_OPTIONS) as { patches?: Catalog } | null;
  const patches = parsed?.patches ?? {};
  for (const entry of Object.values(patches)) {
    const captured: unknown = entry.captured;
    entry.captured = captured instanceof Date ? captured.toISOString().slice(0, 19) : String(captured ?? "");
  }
  return patches;
}

function writeAtomically(file: string, text: string): void {
  const temporary = `${file}.tmp`;
  fs.writeFileSync(temporary, text);
  fs.renameSync(temporary, file); // a crash cannot leave half a file
}

function saveCatalog(patches: Catalog): void {
  fs.mkdirSync(LIBRARY, { recursive: true });
  writeAtomically(CATALOG, HEADER + YAML.stringify({ patches }, { ...YAML_OPTIONS, lineWidth: 100 }));
}

// Setlist ---------------------------------------------------------------------------------------

function readSetlist(): string[] {
  if (!fs.existsSync(SETLIST)) return [];
  return fs
    .readFileSync(SETLIST, "utf8")
    .split("\n")
    .map((line) => line.split("#")[0].trim()) // whatever follows a # is a comment
    .filter(Boolean);
}

function writeSetlist(keys: string[], patches: Catalog = loadCatalog()): void {
  const lines = [
    "# One dump name per line, in performance order. Blank lines and # comments are ignored.",
    "# The text after # is only a reminder. This file is also written by the web page (npm start in web/).",
    "",
  ];
  for (const key of keys) {
    const e = patches[key];
    lines.push(e ? `${key}    # ${e.title}  |  ${e.tone ?? ""}` : key);
  }
  writeAtomically(SETLIST, lines.join("\n") + "\n");
}

// Is a capture running? Examines the arguments of each process: matching text on the command line
// would also match a shell or editor whose command merely mentions it.
function captureRunning(): boolean {
  let entries: string[];
  try {
    entries = fs.readdirSync("/proc");
  } catch {
    return false;
  }
  for (const entry of entries) {
    if (!/^\d+$/.test(entry) || Number(entry) === process.pid) continue;
    let argv: string[];
    try {
      argv = fs.readFileSync(`/proc/${entry}/cmdline`, "utf8").split("\0").filter(Boolean);
    } catch {
      continue;
    }
    if (
      argv.length >= 3 &&
      path.basename(argv[0]).startsWith("python") &&
      argv.slice(1).some((a) => path.basename(a) === "collect_library.py") &&
      argv.includes("capture")
    ) {
      return true;
    }
  }
  return false;
}

// What the page shows ---------------------------------------------------------------------------

export function pageData(): PageData {
  const patches = loadCatalog();
  const order = Object.keys(patches).sort((a, b) => (patches[a].captured < patches[b].captured ? -1 : patches[a].captured > patches[b].captured ? 1 : 0));
  const data: PageData = { patches: {}, order, saved: readSetlist(), capture_running: captureRunning() };
  for (const key of order) {
    const e = patches[key];
    const f = filesOf(key);
    const text = (name: string): string => String(e[name] ?? "");
    data.patches[key] = {
      title: text("title"),
      tone: text("tone"),
      effect: text("effect"),
      level: text("level"),
      other: text("other"),
      notes: text("notes"),
      tags: (e.tags ?? []).map(String),
      reviewed: Boolean(e.reviewed),
      touche: String(e.touche ?? ""),
      photo: fs.existsSync(f.photo) ? `photos/${encodeURIComponent(key)}.jpg` : "",
      audio: fs.existsSync(f.audio) ? `audio/${encodeURIComponent(key)}.ogg` : "",
    };
  }
  return data;
}

type Fields = Partial<Record<(typeof EDITABLE)[number], string>> & { tags?: string[]; reviewed?: boolean };

// Apply edits to one catalog entry. A new title renames the entry, its files and its setlist line.
function editPatch(key: string, fields: Fields): string {
  const patches = loadCatalog();
  if (!(key in patches)) throw new HttpError(404, `no patch named '${key}'`);
  const entry = patches[key];
  const newTitle = String(fields.title ?? "").trim();
  let newKey = key;
  if ("title" in fields && newTitle && safe(newTitle) !== key) {
    newKey = safe(newTitle);
    if (newKey in patches || fs.existsSync(filesOf(newKey).dump)) {
      throw new HttpError(409, `nothing saved: a patch called '${newKey}' already exists`);
    }
  }
  for (const name of EDITABLE) if (name in fields) entry[name] = String(fields[name]).trim();
  if ("tags" in fields) entry.tags = (fields.tags ?? []).map((t) => String(t).trim()).filter(Boolean);
  if ("reviewed" in fields) entry.reviewed = Boolean(fields.reviewed);

  if (newKey === key) {
    saveCatalog(patches);
    return "saved";
  }
  // Move the files first, then the catalog entry (in place, so the file keeps its order) and the setlist line.
  const from = filesOf(key);
  const to = filesOf(newKey);
  const moved: (keyof typeof from)[] = [];
  try {
    for (const kind of ["dump", "photo", "audio"] as const) {
      if (fs.existsSync(from[kind])) {
        fs.renameSync(from[kind], to[kind]);
        moved.push(kind);
      }
    }
  } catch (e) {
    for (const kind of moved) fs.renameSync(to[kind], from[kind]); // undo
    throw new HttpError(500, `could not rename the files: ${(e as Error).message}`);
  }
  const renamed: Catalog = {};
  for (const [k, v] of Object.entries(patches)) renamed[k === key ? newKey : k] = v;
  saveCatalog(renamed);
  const setlist = readSetlist();
  if (setlist.includes(key)) writeSetlist(setlist.map((k) => (k === key ? newKey : k)), renamed);
  return `saved, renamed to ${newKey}`;
}

// Requests --------------------------------------------------------------------------------------

export function json(status: number, body: unknown, headers: Record<string, string> = {}): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
  });
}

// Run a handler and turn what it throws into a JSON error response.
export async function respond(handler: () => Response | Promise<Response>): Promise<Response> {
  try {
    return await handler();
  } catch (e) {
    if (e instanceof HttpError) return json(e.status, { error: e.message });
    return json(500, { error: `${(e as Error).name}: ${(e as Error).message}` });
  }
}

// A request may only come from this machine, and a write only from the page itself.
function checkLocal(request: Request): void {
  const host = request.headers.get("host") ?? "";
  if (!["127.0.0.1", "localhost"].includes(host.replace(/:\d+$/, ""))) throw new HttpError(403, "unexpected host");
}
function checkWrite(request: Request, guardCapture = true): void {
  checkLocal(request);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host")) throw new HttpError(403, "refused: another site");
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    throw new HttpError(403, "refused: not a request from the page");
  }
  if (guardCapture && captureRunning()) throw new HttpError(409, "a capture is running: changes are disabled until it stops");
}

export const getData = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    return json(200, pageData());
  });

export const postPatch = (request: Request): Promise<Response> =>
  respond(async () => {
    checkWrite(request);
    const body = (await request.json()) as { key: unknown; fields?: Fields };
    const message = editPatch(String(body.key), body.fields ?? {});
    return json(200, { ...pageData(), message });
  });

export const postSetlist = (request: Request): Promise<Response> =>
  respond(async () => {
    checkWrite(request);
    const body = (await request.json()) as { list?: unknown };
    if (!Array.isArray(body.list)) throw new HttpError(400, "list must be an array");
    writeSetlist(body.list.map(String));
    return json(200, { ...pageData(), message: "saved" });
  });

// A photo or an audio file, with range requests: browsers ask for ranges to play and seek audio.
export function media(request: Request, kind: keyof typeof MEDIA, name: string): Promise<Response> {
  return respond(() => {
    checkLocal(request);
    const folder = MEDIA[kind];
    const full = path.resolve(folder, name);
    // Judged on the resolved path, so no .. tricks get out of the folder.
    if (!full.startsWith(folder + path.sep) || !fs.existsSync(full) || !fs.statSync(full).isFile()) {
      throw new HttpError(404, "not found");
    }
    const data = fs.readFileSync(full);
    const type = path.extname(full) === ".jpg" ? "image/jpeg" : path.extname(full) === ".ogg" ? "audio/ogg" : "application/octet-stream";
    const range = /^bytes=(\d*)-(\d*)$/.exec(request.headers.get("range") ?? "");
    if (range && (range[1] || range[2])) {
      const start = range[1] ? Number(range[1]) : Math.max(0, data.length - Number(range[2]));
      const end = range[1] && range[2] ? Math.min(Number(range[2]), data.length - 1) : data.length - 1;
      return new Response(new Uint8Array(data.subarray(start, end + 1)), {
        status: 206,
        headers: { "Content-Type": type, "Content-Range": `bytes ${start}-${end}/${data.length}`, "Accept-Ranges": "bytes", "Cache-Control": "no-store" },
      });
    }
    return new Response(new Uint8Array(data), { status: 200, headers: { "Content-Type": type, "Accept-Ranges": "bytes", "Cache-Control": "no-store" } });
  });
}

// The results of the bridge page's target test: one entry per target id, kept next to the library.
const TARGET_TESTS = path.join(LIBRARY, "target-tests.json");

function readTargetTests(): Record<string, unknown> {
  if (!fs.existsSync(TARGET_TESTS)) return {};
  return JSON.parse(fs.readFileSync(TARGET_TESTS, "utf8")) as Record<string, unknown>;
}

export const getTargetTests = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    return json(200, readTargetTests());
  });

export const postTargetTest = (request: Request): Promise<Response> =>
  respond(async () => {
    checkWrite(request, false); // these results do not touch the catalog, so a running capture is no reason to refuse
    const body = (await request.json()) as { id?: unknown; result?: unknown; clear?: unknown };
    let tests = readTargetTests();
    if (body.clear === true) {
      tests = {};
    } else {
      if (typeof body.id !== "string" || !/^[\w.-]{1,80}$/.test(body.id)) throw new HttpError(400, "id must be a target id");
      if (typeof body.result !== "object" || body.result === null || Array.isArray(body.result)) throw new HttpError(400, "result must be an object");
      tests[body.id] = body.result;
    }
    writeAtomically(TARGET_TESTS, JSON.stringify(tests, null, 2) + "\n");
    return json(200, tests);
  });

// The live log of the bridge page: its steps are appended here as one JSON object per line, so that they can be
// followed while a test runs (tail -F library/page-log.jsonl). The file is rotated when it passes 1 MB.
const PAGE_LOG = path.join(LIBRARY, "page-log.jsonl");

export const postPageLog = (request: Request): Promise<Response> =>
  respond(async () => {
    checkWrite(request, false);
    const body = (await request.json()) as { events?: unknown };
    if (!Array.isArray(body.events) || body.events.length > 200) throw new HttpError(400, "events must be a list of at most 200");
    const lines = body.events.map((e) => {
      const event = e as { t?: unknown; kind?: unknown; text?: unknown };
      return JSON.stringify({ t: Number(event.t) || Date.now(), kind: String(event.kind ?? "").slice(0, 20), text: String(event.text ?? "").slice(0, 2000) });
    });
    fs.mkdirSync(LIBRARY, { recursive: true });
    if (fs.existsSync(PAGE_LOG) && fs.statSync(PAGE_LOG).size > 1_000_000) fs.renameSync(PAGE_LOG, `${PAGE_LOG}.1`);
    fs.appendFileSync(PAGE_LOG, lines.join("\n") + "\n");
    return json(200, { ok: true });
  });

// Pairings: which Touché remap template goes with which registration (a library patch) ---------------------

export interface TemplateInfo {
  name: string;
  patch_type: string;
  status: string;
  dead_axes: number[];
}
export interface Suggestion {
  template: string;
  reason: string;
}
export interface PairingData {
  templates: TemplateInfo[];
  order: string[];
  titles: Record<string, string>;
  pairings: Record<string, string>;
  suggestions: Record<string, Suggestion>;
  capture_running: boolean;
  message?: string;
}

// The templates are generated by tools/make_templates.py into web/public/maps; the dev server runs in web/.
function readTemplates(): TemplateInfo[] {
  const file = path.join(process.cwd(), "public", "maps", "index.json");
  if (!fs.existsSync(file)) return [];
  const index = JSON.parse(fs.readFileSync(file, "utf8")) as Partial<TemplateInfo>[];
  const templates = index.map((t) => ({ name: String(t.name), patch_type: String(t.patch_type ?? ""), status: String(t.status ?? ""), dead_axes: t.dead_axes ?? [] }));
  return withSavedMappings(templates);
}

// Because the mappings saved from the editor page take the place of the templates of the same name, the pairings
// list them too: a template saved over is marked, and a mapping saved under a new name is added.
function withSavedMappings(templates: TemplateInfo[]): TemplateInfo[] {
  const known = new Set<string>();
  for (const t of templates) known.add(t.name);
  for (const info of listMappings()) {
    if (info.source === "saved over a template") {
      for (const t of templates) if (t.name === info.name) t.status = "edited in the mapping editor";
    } else if (info.source === "saved" && !known.has(info.name)) {
      templates.push({ name: info.name, patch_type: info.patch_type, status: "saved from the mapping editor", dead_axes: [] });
    }
  }
  return templates;
}

// The first address of each part block and the offsets inside it: 00 mute (0 means it sounds), 01 tone number, 02 and 03 bank bytes.
const PARTS = {
  organ: ["organ_upper", 0x8000],
  piano: ["upper_piano", 0x4080],
  synth: ["upper_synth", 0x4180],
  synth2: ["upper_synth_dual2", 0x4100],
  lowerSynth: ["lower_synth", 0x4980],
} as const;

// The mapping follows the sections that sound: each one drives only targets the unit accepts on those sections
// (the section-* templates of tools/make_templates.py). Organs keep the organ templates, whose drawbars all work.
function suggest(key: string, templates: TemplateInfo[]): Suggestion {
  const f = filesOf(key).dump;
  if (!fs.existsSync(f)) return { template: "", reason: "no dump" };
  const dump = JSON.parse(fs.readFileSync(f, "utf8")) as Record<string, number>;
  const at = (part: keyof typeof PARTS, offset: number): number | undefined => {
    const [block, base] = PARTS[part];
    return dump[`${block}:${(base + offset).toString(16).toUpperCase().padStart(8, "0")}`];
  };
  const sounds = (part: keyof typeof PARTS): boolean => at(part, 0) === 0;
  const organ = sounds("organ"), piano = sounds("piano"), synth = sounds("synth"), synth2 = sounds("synth2"), lower = sounds("lowerSynth");
  const known = new Set(templates.map((x) => x.name));
  const pick = (name: string, reason: string): Suggestion => ({ template: known.has(name) ? name : "", reason });

  if (organ && piano) return pick("xfade-piano-organ", "the organ and the upper piano sound");
  if (organ && (synth || synth2)) return pick("xfade-organ-synth", "the organ and an upper synth sound");
  if (organ && lower) return pick("section-organ-split", "the organ sounds over a lower synth");
  if (organ) return pick("organ-brightness-sweep", "the organ sounds");
  if (piano && synth2) return pick("section-piano-layer", "the upper piano sounds with a synth dual 2 layer");
  if (piano && lower) return pick("section-piano-split", "the upper piano sounds over a lower synth");
  if (piano) return pick("section-piano", "the upper piano sounds alone");
  if (synth && synth2) return pick("section-synth-layers", "the upper synth sounds with its dual 2 layer");
  if (synth && lower) return pick("section-synth-split", "the upper synth sounds over a lower synth");
  if (synth || synth2) return pick("section-synth", "one upper synth sounds");
  return pick("perform-expression-reverb", "no organ, piano or synth section sounds (a drum patch)");
}

function pairingData(): PairingData {
  const patches = loadCatalog();
  const templates = readTemplates();
  const order = Object.keys(patches).sort((a, b) => (patches[a].captured < patches[b].captured ? -1 : patches[a].captured > patches[b].captured ? 1 : 0));
  const data: PairingData = { templates, order, titles: {}, pairings: {}, suggestions: {}, capture_running: captureRunning() };
  for (const key of order) {
    data.titles[key] = String(patches[key].title ?? "");
    if (patches[key].touche) data.pairings[key] = String(patches[key].touche);
    data.suggestions[key] = suggest(key, templates);
  }
  return data;
}

type PairingRequest = { key?: unknown; template?: unknown; suggest?: unknown };

function applyPairing(body: PairingRequest): string {
  const patches = loadCatalog();
  const templates = readTemplates();
  if (body.suggest === "unpaired" || body.suggest === "all") {
    let count = 0;
    for (const key of Object.keys(patches)) {
      if (patches[key].touche && body.suggest === "unpaired") continue;
      const s = suggest(key, templates);
      if (!s.template) continue;
      patches[key].touche = s.template;
      count += 1;
    }
    saveCatalog(patches);
    return `${count} patches paired from the sections that sound`;
  }
  const key = String(body.key);
  if (!(key in patches)) throw new HttpError(404, `no patch named '${key}'`);
  if (body.template === null || body.template === "") {
    delete patches[key].touche;
    saveCatalog(patches);
    return "pairing removed";
  }
  const template = String(body.template);
  if (!templates.some((x) => x.name === template)) throw new HttpError(400, `no template named '${template}'`);
  patches[key].touche = template;
  saveCatalog(patches);
  return "paired";
}

export const getPairings = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    return json(200, pairingData());
  });

export const postPairing = (request: Request): Promise<Response> =>
  respond(async () => {
    checkWrite(request);
    const message = applyPairing((await request.json()) as PairingRequest);
    return json(200, { ...pairingData(), message });
  });

function libraryDumps(patches: Catalog): Record<string, Dump> {
  const dumps: Record<string, Dump> = {};
  for (const k of Object.keys(patches)) {
    const file = filesOf(k).dump;
    if (fs.existsSync(file)) dumps[k] = JSON.parse(fs.readFileSync(file, "utf8")) as Dump;
  }
  return dumps;
}

// What the page's "Load scene" writes to the VR-09: the messages of vr09.py's recall for one patch of the library.
export const getRecall = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    const key = new URL(request.url).searchParams.get("key") ?? "";
    const patches = loadCatalog();
    if (!(key in patches)) throw new HttpError(404, `no patch named '${key}'`);
    const messages = recallMessages(libraryDumps(patches), key);
    return json(200, { key, title: patches[key].title, template: String(patches[key].touche ?? ""), messages });
  });

// Single tones: one tone of Roland's list, played alone. A library patch where only that section sounds, with every
// sound-shaping value at 64 (no change), is recalled first; then the tone number and bank are written into its part.
interface Tone {
  section: string;
  group: string | null;
  name: string;
  tone_number: number;
  bank_msb: number;
  bank_lsb: number;
}
const TONE_BASES: Record<string, { key: string; address: number[] }> = {
  synth: { key: "14-3_Native_Lead", address: [0x01, 0x03, 0x01] },
  piano: { key: "13-2_Comp_Piano", address: [0x01, 0x01, 0x01] },
};

function readTones(): Tone[] {
  return JSON.parse(fs.readFileSync(path.join(ROOT, "docs", "tones.json"), "utf8")) as Tone[];
}

export const getTones = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    const tones = readTones()
      .map((tone, index) => ({ index, ...tone }))
      .filter((tone) => tone.section in TONE_BASES);
    return json(200, { tones });
  });

export const getToneRecall = (request: Request): Promise<Response> =>
  respond(() => {
    checkLocal(request);
    const index = Number(new URL(request.url).searchParams.get("index"));
    const tone = readTones()[index];
    if (!Number.isInteger(index) || !tone) throw new HttpError(404, "no tone with this index");
    const base = TONE_BASES[tone.section];
    if (!base) throw new HttpError(400, `the ${tone.section} section cannot be played as a single tone`);
    const patches = loadCatalog();
    if (!(base.key in patches)) throw new HttpError(500, `the base patch '${base.key}' is not in the library`);
    const messages = recallMessages(libraryDumps(patches), base.key);
    messages.push(dt1Message(base.address, [tone.tone_number, tone.bank_msb, tone.bank_lsb]));
    return json(200, { tone, base: base.key, messages });
  });

// Mappings ---------------------------------------------------------------------------------------
// A mapping says what each Touché axis drives on the VR-09. The generated templates live in web/public/maps and
// are rewritten by tools/make_templates.py, so the mappings edited in the editor page are saved apart, in
// library/mappings. A saved mapping with the name of a template takes its place everywhere (editor, bridge page,
// pairings), and the template file itself is never changed.

const MAPPINGS = path.join(LIBRARY, "mappings");
const TEMPLATES = path.join(process.cwd(), "public", "maps", "templates");
const CURVES = ["linear", "soft", "hard"];

export interface MappingTarget {
  target: string;
  low: number;
  high: number;
  window: [number, number];
  curve: string;
}
export interface MappingAxis {
  axis: number;
  role?: string;
  targets: MappingTarget[];
}
export interface Mapping {
  name: string;
  patch_type?: string;
  summary?: string;
  axes: MappingAxis[];
}
export interface MappingInfo {
  name: string;
  source: "template" | "saved" | "saved over a template";
  patch_type: string;
  summary: string;
}

function mappingFile(name: string): string {
  return path.join(MAPPINGS, `${name}.json`);
}

function templateFile(name: string): string {
  return path.join(TEMPLATES, `${name}.json`);
}

function checkMappingName(name: string): string {
  if (!name || safe(name) !== name) throw new HttpError(400, "a mapping name may only hold letters, digits, - and _");
  return name;
}

function readJsonFile(file: string): Mapping {
  return JSON.parse(fs.readFileSync(file, "utf8")) as Mapping;
}

function infoOf(mapping: Mapping, source: MappingInfo["source"]): MappingInfo {
  return { name: mapping.name, source, patch_type: String(mapping.patch_type ?? ""), summary: String(mapping.summary ?? "") };
}

function jsonNames(folder: string): string[] {
  if (!fs.existsSync(folder)) return [];
  const names: string[] = [];
  for (const file of fs.readdirSync(folder)) if (file.endsWith(".json")) names.push(file.slice(0, -5));
  return names.sort();
}

export function listMappings(): MappingInfo[] {
  const saved = new Set(jsonNames(MAPPINGS));
  const list: MappingInfo[] = [];
  for (const name of jsonNames(TEMPLATES)) {
    if (saved.has(name)) list.push(infoOf(readJsonFile(mappingFile(name)), "saved over a template"));
    else list.push(infoOf(readJsonFile(templateFile(name)), "template"));
  }
  const templates = new Set(jsonNames(TEMPLATES));
  for (const name of saved) if (!templates.has(name)) list.push(infoOf(readJsonFile(mappingFile(name)), "saved"));
  return list;
}

export function readMapping(name: string): Mapping {
  checkMappingName(name);
  if (fs.existsSync(mappingFile(name))) return readJsonFile(mappingFile(name));
  if (fs.existsSync(templateFile(name))) return readJsonFile(templateFile(name));
  throw new HttpError(404, `no mapping named '${name}'`);
}

function checkNumber(value: unknown, what: string): number {
  if (typeof value !== "number" || !Number.isFinite(value)) throw new HttpError(400, `${what} must be a number`);
  return value;
}

// Because a saved mapping is used live by the bridge, it is checked field by field before it is written.
function checkMapping(body: unknown): Mapping {
  const raw = body as Partial<Mapping>;
  const name = checkMappingName(String(raw?.name ?? ""));
  if (!Array.isArray(raw.axes)) throw new HttpError(400, "axes must be a list");
  const axes: MappingAxis[] = [];
  for (const axis of raw.axes) {
    const number = checkNumber(axis.axis, "axis");
    if (![16, 17, 18, 19].includes(number)) throw new HttpError(400, `unknown axis CC${number}`);
    if (!Array.isArray(axis.targets)) throw new HttpError(400, `the targets of CC${number} must be a list`);
    const targets: MappingTarget[] = [];
    for (const t of axis.targets) {
      if (typeof t.target !== "string" || !t.target) throw new HttpError(400, "every target needs an id");
      if (!Array.isArray(t.window) || t.window.length !== 2) throw new HttpError(400, `the window of ${t.target} must be two numbers`);
      const curve = String(t.curve ?? "linear");
      if (!CURVES.includes(curve)) throw new HttpError(400, `unknown curve '${curve}'`);
      targets.push({
        target: t.target,
        low: checkNumber(t.low, "low"),
        high: checkNumber(t.high, "high"),
        window: [checkNumber(t.window[0], "window start"), checkNumber(t.window[1], "window end")],
        curve,
      });
    }
    axes.push({ axis: number, role: axis.role ? String(axis.role) : undefined, targets });
  }
  return { name, patch_type: raw.patch_type ? String(raw.patch_type) : undefined, summary: raw.summary ? String(raw.summary) : undefined, axes };
}

function saveMapping(body: unknown): Mapping {
  const mapping = checkMapping(body);
  fs.mkdirSync(MAPPINGS, { recursive: true });
  writeAtomically(mappingFile(mapping.name), JSON.stringify(mapping, null, 1) + "\n");
  return mapping;
}

function mappingListResponse(request: Request): Response {
  checkLocal(request);
  return json(200, { mappings: listMappings() });
}

function mappingReadResponse(request: Request): Response {
  checkLocal(request);
  return json(200, readMapping(new URL(request.url).searchParams.get("name") ?? ""));
}

async function mappingWriteResponse(request: Request): Promise<Response> {
  checkWrite(request, false);
  const mapping = saveMapping(await request.json());
  return json(200, { mapping, mappings: listMappings() });
}

export function getMappings(request: Request): Promise<Response> {
  return respond(mappingListResponse.bind(null, request));
}

export function getMapping(request: Request): Promise<Response> {
  return respond(mappingReadResponse.bind(null, request));
}

export function postMapping(request: Request): Promise<Response> {
  return respond(mappingWriteResponse.bind(null, request));
}
