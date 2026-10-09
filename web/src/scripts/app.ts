// The library page: patches as cards, a setlist builder, double-click editing, and a compact audio preview.
interface Patch {
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
interface PageData {
  patches: Record<string, Patch>;
  order: string[];
  saved: string[];
  capture_running: boolean;
  message?: string;
}
type Fields = Partial<Record<"title" | "tone" | "effect" | "level" | "other" | "notes", string>> & { tags?: string[]; reviewed?: boolean };

let P: Record<string, Patch> = {};
let order: string[] = [];
let setlist: string[] = [];
let editing: string | null = null;
let locked = false;

const $ = <T extends HTMLElement = HTMLElement>(id: string): T => document.getElementById(id) as T;
const esc = (s: unknown): string =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] as string);
const library = $("library"), items = $("items"), q = $<HTMLInputElement>("q"), todo = $<HTMLInputElement>("todo");

// Messages -----------------------------------------------------------------------------------------
let toastTimer: number | undefined;
function toast(text: string, bad = false): void {
  const t = $("toast");
  t.textContent = text;
  t.className = "show" + (bad ? " bad" : "");
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => (t.className = ""), bad ? 5000 : 1800);
}
async function post(path: string, body: unknown): Promise<PageData> {
  let r: Response;
  let data: PageData & { error?: string };
  try {
    r = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    data = await r.json();
  } catch (e) {
    toast("could not reach the server: " + e, true);
    throw e;
  }
  if (!r.ok) {
    toast(data.error ?? "error " + r.status, true);
    throw new Error(data.error ?? String(r.status));
  }
  return data;
}

// The audio preview: one shared player, so only one preview plays at a time ------------------------
const ICON = {
  play: '<svg viewBox="0 0 16 16"><path d="M4 2.5v11l9-5.5z" fill="currentColor"/></svg>',
  stop: '<svg viewBox="0 0 16 16"><rect x="3.5" y="3.5" width="9" height="9" rx="1" fill="currentColor"/></svg>',
  sound: '<svg viewBox="0 0 16 16"><path d="M2 6h3l4-3v10l-4-3H2z" fill="currentColor"/><path d="M11 5.5a3.5 3.5 0 0 1 0 5M12.6 3.6a6 6 0 0 1 0 8.8" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  muted: '<svg viewBox="0 0 16 16"><path d="M2 6h3l4-3v10l-4-3H2z" fill="currentColor"/><path d="M11 6l4 4M15 6l-4 4" fill="none" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
};
const player = new Audio();
player.preload = "none";
let current: string | null = null; // the url being played
let volume = 0.8;
let lastVolume = 0.8;
try {
  const saved = localStorage.getItem("vr09-volume");
  if (saved !== null && Number(saved) >= 0 && Number(saved) <= 1) volume = Number(saved);
} catch {
  /* no storage: the volume just is not kept */
}
if (volume > 0) lastVolume = volume;
player.volume = volume;

function playerHtml(url: string): string {
  if (!url) return `<span class="none">no preview</span>`;
  return (
    `<span class="mini"><button class="play" data-url="${esc(url)}" title="Play / stop" aria-label="Play or stop the preview">${ICON.play}</button>` +
    `<span class="vol"><button class="volbtn" title="Volume (click to mute)" aria-label="Volume">${volume === 0 ? ICON.muted : ICON.sound}</button>` +
    `<input class="volrange" type="range" min="0" max="1" step="0.05" value="${volume}" aria-label="Volume"></span></span>`
  );
}
function refreshPlayers(): void {
  for (const b of document.querySelectorAll<HTMLButtonElement>(".play")) {
    const on = b.dataset.url === current && !player.paused;
    b.classList.toggle("playing", on);
    b.innerHTML = on ? ICON.stop : ICON.play;
  }
  for (const b of document.querySelectorAll(".volbtn")) b.innerHTML = volume === 0 ? ICON.muted : ICON.sound;
  for (const r of document.querySelectorAll<HTMLInputElement>(".volrange")) r.value = String(volume);
}
function setVolume(v: number): void {
  volume = Math.min(1, Math.max(0, v));
  if (volume > 0) lastVolume = volume;
  player.volume = volume;
  try {
    localStorage.setItem("vr09-volume", String(volume));
  } catch {
    /* see above */
  }
  refreshPlayers();
}
function togglePlay(url: string): void {
  if (current === url && !player.paused) {
    player.pause();
    player.currentTime = 0;
    current = null;
  } else {
    current = url;
    player.src = url;
    player.play().catch(() => {
      current = null;
      refreshPlayers();
      toast("the preview could not be played", true);
    });
  }
  refreshPlayers();
}
for (const event of ["ended", "pause", "play", "error"]) player.addEventListener(event, refreshPlayers);
player.addEventListener("ended", () => {
  current = null;
  refreshPlayers();
});

document.addEventListener("click", (e) => {
  const target = e.target as Element;
  const play = target.closest<HTMLElement>(".play");
  const mute = target.closest<HTMLElement>(".volbtn");
  if (play) togglePlay(play.dataset.url ?? "");
  else if (mute) {
    setVolume(volume > 0 ? 0 : lastVolume);
    mute.closest(".vol")?.classList.add("open"); // for touch screens, where there is no hover
  } else for (const v of document.querySelectorAll(".vol.open")) v.classList.remove("open");
});
document.addEventListener("input", (e) => {
  const target = e.target as HTMLInputElement;
  if (target.matches(".volrange")) setVolume(Number(target.value));
});

// Data ---------------------------------------------------------------------------------------------
function applyData(d: PageData): void {
  P = d.patches;
  order = d.order;
  setlist = d.saved;
  locked = d.capture_running;
  $("lock").hidden = !locked;
  if (editing && !P[editing]) editing = null;
  renderLibrary();
  renderSetlist();
}
async function load(): Promise<void> {
  applyData(await (await fetch("/api/data")).json());
}

// Library ------------------------------------------------------------------------------------------
const photoHtml = (p: Patch): string => (p.photo ? `<img src="${esc(p.photo)}" alt="" loading="lazy">` : "");

function cardHtml(key: string): string {
  const p = P[key];
  const at = setlist.indexOf(key) + 1;
  if (key === editing) return editHtml(key);
  const rows = (["tone", "effect", "level", "other"] as const)
    .filter((f) => p[f])
    .map((f) => `<div class="row">${f}: <b>${esc(p[f])}</b></div>`)
    .join("");
  const extra =
    (p.tags.length ? `<div class="row">tags: <b>${esc(p.tags.join(", "))}</b></div>` : "") +
    (p.notes ? `<div class="row">notes: <b>${esc(p.notes)}</b></div>` : "");
  const text = [p.title, p.tone, p.effect, p.level, p.other, p.notes, p.tags.join(" "), key].join(" ").toLowerCase();
  return `<article class="card" data-key="${esc(key)}" data-reviewed="${p.reviewed ? "yes" : "no"}" data-text="${esc(text)}">
    ${photoHtml(p)}
    <div class="body"><div class="title">${esc(p.title || "(no title)")}</div><div class="key">${esc(key)}</div>${rows}${extra}
    <button class="badge ${p.reviewed ? "done" : "todo"}" data-act="reviewed" title="Click to mark as ${p.reviewed ? "not reviewed" : "reviewed"}">${p.reviewed ? "reviewed" : "not reviewed"}</button>
    <div class="actions"><button data-act="toggle">${at ? "Remove from setlist" : "Add to setlist"}</button>${at ? `<span class="in">no. ${at}</span>` : ""}${playerHtml(p.audio)}</div>
    <div class="hintline">double-click the card to edit</div></div></article>`;
}
function editHtml(key: string): string {
  const p = P[key];
  const field = (name: keyof Patch, label: string, value?: string): string =>
    `<label class="f">${label}<input name="${name}" value="${esc(value ?? p[name])}" autocomplete="off"></label>`;
  return `<article class="card editing" data-key="${esc(key)}" data-reviewed="${p.reviewed ? "yes" : "no"}" data-text="">
    ${photoHtml(p)}
    <form class="body" data-key="${esc(key)}">
      <div class="key">${esc(key)}</div>
      ${field("title", "title (slot and name; changing it renames the files)")}
      ${field("tone", "tone")}${field("effect", "effect")}${field("level", "level")}${field("other", "other")}
      ${field("tags", "tags, separated by commas", p.tags.join(", "))}
      <label class="f">notes<textarea name="notes">${esc(p.notes)}</textarea></label>
      <label class="check"><input type="checkbox" name="reviewed" ${p.reviewed ? "checked" : ""}> reviewed</label>
      <div class="actions"><button type="submit" class="primary">Save</button><button type="button" data-act="cancel">Cancel</button>
      <span class="hintline">Esc cancels</span></div>
    </form></article>`;
}
function renderLibrary(): void {
  library.innerHTML = order.map(cardHtml).join("");
  applyFilter();
  refreshPlayers();
}
function applyFilter(): void {
  const words = q.value.toLowerCase().split(/\s+/).filter(Boolean);
  let shown = 0;
  for (const c of Array.from(library.children) as HTMLElement[]) {
    const ok = c.classList.contains("editing") || (words.every((w) => (c.dataset.text ?? "").includes(w)) && (!todo.checked || c.dataset.reviewed === "no"));
    c.hidden = !ok;
    if (ok) shown++;
  }
  $("count").textContent = shown + " of " + order.length + " patches";
}

// Setlist ------------------------------------------------------------------------------------------
function renderSetlist(): void {
  $("setlist-count").textContent = "(" + setlist.length + ")";
  if (!setlist.length) {
    items.innerHTML = `<li class="empty">The setlist is empty. Add patches from the Library tab.</li>`;
    return;
  }
  items.innerHTML = setlist
    .map((key, i) => {
      const p = P[key];
      const controls = `<div class="controls"><button data-act="up" ${i === 0 ? "disabled" : ""} title="Move up">&#9650;</button>
      <button data-act="down" ${i === setlist.length - 1 ? "disabled" : ""} title="Move down">&#9660;</button>
      <button data-act="remove" title="Remove">&#10005;</button></div>`;
      if (!p) {
        return `<li class="item missing" data-key="${esc(key)}"><span class="num">${i + 1}</span><span></span>
      <div class="info"><div class="text"><div class="title">${esc(key)}</div><div class="row">not in the catalog (renamed or removed?)</div></div></div>${controls}</li>`;
      }
      return `<li class="item" data-key="${esc(key)}"><span class="num">${i + 1}</span>
      ${p.photo ? `<img src="${esc(p.photo)}" alt="" loading="lazy">` : "<span></span>"}
      <div class="info"><div class="text"><div class="title">${esc(p.title)}</div><div class="row">${esc([p.tone, p.effect].filter(Boolean).join("  |  "))}</div></div>${p.audio ? playerHtml(p.audio) : ""}</div>${controls}</li>`;
    })
    .join("");
  refreshPlayers();
}
async function saveSetlist(list: string[]): Promise<void> {
  const data = await post("/api/setlist", { list });
  applyData(data);
  toast("setlist saved, " + data.saved.length + " patches");
}
async function saveFields(key: string, fields: Fields, message?: string): Promise<void> {
  const data = await post("/api/patch", { key, fields });
  editing = null;
  applyData(data);
  toast(data.message ?? message ?? "saved");
}

// Events -------------------------------------------------------------------------------------------
library.addEventListener("click", (e) => {
  const button = (e.target as Element).closest<HTMLElement>("button[data-act]");
  const card = button?.closest<HTMLElement>(".card");
  if (!button || !card) return;
  const key = card.dataset.key ?? "";
  const act = button.dataset.act;
  if (act === "cancel") {
    editing = null;
    renderLibrary();
  } else if (act === "reviewed") {
    saveFields(key, { reviewed: !P[key].reviewed }, P[key].reviewed ? "marked not reviewed" : "marked reviewed").catch(() => {});
  } else if (act === "toggle") {
    saveSetlist(setlist.includes(key) ? setlist.filter((k) => k !== key) : setlist.concat([key])).catch(() => {});
  }
});
library.addEventListener("dblclick", (e) => {
  const card = (e.target as Element).closest<HTMLElement>(".card");
  if (!card || (e.target as Element).closest("button, audio, input, textarea, label, .mini")) return;
  if (locked) {
    toast("a capture is running: changes are disabled", true);
    return;
  }
  editing = card.dataset.key ?? null;
  renderLibrary();
  const field = library.querySelector<HTMLInputElement>(".card.editing input[name=title]");
  field?.focus();
  field?.select();
});
library.addEventListener("submit", (e) => {
  e.preventDefault();
  const form = e.target as HTMLFormElement;
  const key = form.dataset.key ?? "";
  const p = P[key];
  const fields: Fields = {};
  const value = (name: string): string => (form.elements.namedItem(name) as HTMLInputElement).value.trim();
  for (const name of ["title", "tone", "effect", "level", "other", "notes"] as const) if (value(name) !== (p[name] || "")) fields[name] = value(name);
  const tags = value("tags").split(",").map((t) => t.trim()).filter(Boolean);
  if (tags.join("|") !== p.tags.join("|")) fields.tags = tags;
  const reviewed = (form.elements.namedItem("reviewed") as HTMLInputElement).checked;
  if (reviewed !== p.reviewed) fields.reviewed = reviewed;
  if (!Object.keys(fields).length) {
    editing = null;
    renderLibrary();
    return;
  }
  saveFields(key, fields).catch(() => {});
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && editing) {
    editing = null;
    renderLibrary();
  }
});

items.addEventListener("click", (e) => {
  const button = (e.target as Element).closest<HTMLElement>("button[data-act]");
  const item = button?.closest<HTMLElement>(".item");
  if (!button || !item) return;
  const list = setlist.slice();
  const i = list.indexOf(item.dataset.key ?? "");
  const act = button.dataset.act;
  if (act === "remove") list.splice(i, 1);
  else if (act === "up" && i > 0) [list[i - 1], list[i]] = [list[i], list[i - 1]];
  else if (act === "down" && i < list.length - 1) [list[i + 1], list[i]] = [list[i], list[i + 1]];
  saveSetlist(list).catch(() => {});
});
$("clear").addEventListener("click", () => saveSetlist([]).catch(() => {}));
$("reload").addEventListener("click", () => load().then(() => toast("reloaded")));

function show(tab: "library" | "setlist"): void {
  const onSetlist = tab === "setlist";
  library.hidden = onSetlist;
  $("setlist").hidden = !onSetlist;
  for (const id of ["q", "todo-label", "count"]) $(id).style.display = onSetlist ? "none" : "";
  $("tab-library").classList.toggle("on", !onSetlist);
  $("tab-setlist").classList.toggle("on", onSetlist);
  history.replaceState(null, "", onSetlist ? "#setlist" : "#");
}
$("tab-library").addEventListener("click", () => show("library"));
$("tab-setlist").addEventListener("click", () => show("setlist"));
q.addEventListener("input", applyFilter);
todo.addEventListener("change", applyFilter);

load().then(() => show(location.hash === "#setlist" ? "setlist" : "library"));
