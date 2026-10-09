// The server side of the library page: reads and writes library/catalog.yaml and the setlist file,
// renames patches' files, and answers the page's requests. Used by the API routes in src/pages.
import fs from "node:fs";
import path from "node:path";
import YAML from "yaml";

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
function checkWrite(request: Request): void {
  checkLocal(request);
  const origin = request.headers.get("origin");
  if (origin && new URL(origin).host !== request.headers.get("host")) throw new HttpError(403, "refused: another site");
  if (!(request.headers.get("content-type") ?? "").startsWith("application/json")) {
    throw new HttpError(403, "refused: not a request from the page");
  }
  if (captureRunning()) throw new HttpError(409, "a capture is running: changes are disabled until it stops");
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
