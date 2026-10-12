// The Touché mapping editor: drag a Touché axis onto a VR-09 control to modulate it, shape the modulation with
// the handles of its ring or in the Modulations tab, load a sound and a mapping separately, and play live.
import {
  AXES, AXIS_NAMES, ctx, fileFromMods, isAvailable, isDirty, markSaved, modById, modValue, modsFromFile, modsOfTarget,
  type MappingFile, type MappingInfo, type Mod, type Target,
} from "./state";
import {
  RECALL_GAP_MS, SEND_GAP_MS, applyPorts, dt1, midi, neutralControllers, packedAddress, readBlocks, refreshPorts,
  requestAccess, send, sendAll, sleep,
} from "./midi";
import {
  escapeHtml, redrawTarget, renderMods, renderPanel, renderSelection, renderTouche, transferSvg, updateMeter,
  updateModRowInputs, updateModRowLive,
} from "./view";

function $(id: string): HTMLElement {
  return document.getElementById(id) as HTMLElement;
}

function input(id: string): HTMLInputElement {
  return document.getElementById(id) as HTMLInputElement;
}

function select(id: string): HTMLSelectElement {
  return document.getElementById(id) as HTMLSelectElement;
}

function status(text: string, kind: "" | "ok" | "bad" = ""): void {
  const box = $("status");
  box.textContent = text;
  box.className = kind;
}

function portSelects(): { touche: HTMLSelectElement; vr09In: HTMLSelectElement; vr09Out: HTMLSelectElement } {
  return { touche: select("port-touche"), vr09In: select("port-vr09-in"), vr09Out: select("port-vr09-out") };
}

async function getJson<T>(url: string): Promise<T> {
  const response = await fetch(url);
  const body = (await response.json()) as T & { error?: string };
  if (!response.ok || body.error) throw new Error(body.error ?? `${response.status} ${response.statusText}`);
  return body;
}

// ---------- modal ----------

function storeResolver(resolve: (answer: string) => void): void {
  ctx.modalResolve = resolve;
}

// A small dialog that answers with the label of the button pressed, or "" when it is dismissed. With a default
// value, it also shows a text field, and the answer is then the text.
function ask(message: string, buttons: string[], defaultText?: string): Promise<string> {
  $("modal-message").textContent = message;
  const field = input("modal-input");
  field.hidden = defaultText === undefined;
  field.value = defaultText ?? "";
  let html = "";
  for (let i = 0; i < buttons.length; i++) html += `<button data-answer="${escapeHtml(buttons[i])}" class="${i === 0 ? "primary" : ""}">${escapeHtml(buttons[i])}</button>`;
  $("modal-buttons").innerHTML = html;
  ($("modal") as HTMLDialogElement).showModal();
  if (defaultText !== undefined) field.select();
  return new Promise<string>(storeResolver);
}

function closeModal(answer: string): void {
  ($("modal") as HTMLDialogElement).close();
  const resolve = ctx.modalResolve;
  ctx.modalResolve = null;
  if (!resolve) return;
  if (!input("modal-input").hidden && answer !== "Cancel" && answer !== "") resolve(input("modal-input").value.trim());
  else resolve(answer === "" ? "" : answer);
}

function onModalClick(event: Event): void {
  const button = (event.target as HTMLElement).closest("button");
  if (button && button.dataset.answer !== undefined) closeModal(button.dataset.answer);
}

function onModalCancel(event: Event): void {
  event.preventDefault();
  closeModal("");
}

function onModalKey(event: KeyboardEvent): void {
  if (event.key === "Enter" && !input("modal-input").hidden) {
    event.preventDefault();
    const first = $("modal-buttons").querySelector("button");
    closeModal(first?.dataset.answer ?? "");
  }
}

// ---------- mapping documents ----------

function renderMappingHeader(): void {
  const doc = ctx.doc;
  const dirty = isDirty();
  $("mapping-name").textContent = doc ? doc.name : "no mapping";
  $("mapping-dirty").hidden = !dirty;
  $("mapping-source").textContent = ctx.source;
  input("mapping-type").value = doc?.patch_type ?? "";
  input("mapping-summary").value = doc?.summary ?? "";
  document.title = `${dirty ? "● " : ""}${doc ? doc.name : "Touché mappings"} · Touché mapping editor`;
}

function fillMappingList(): void {
  const groups: [MappingInfo["source"], string][] = [["saved", "Saved"], ["saved over a template", "Templates you edited"], ["template", "Templates"]];
  let html = "";
  for (const [source, label] of groups) {
    html += `<optgroup label="${label}">`;
    for (const info of ctx.mappings) {
      if (info.source === source) html += `<option value="${escapeHtml(info.name)}">${escapeHtml(info.name)}${info.patch_type ? ` (${escapeHtml(info.patch_type)})` : ""}</option>`;
    }
    html += "</optgroup>";
  }
  select("mapping-list").innerHTML = html;
  if (ctx.doc) select("mapping-list").value = ctx.doc.name;
}

function sourceOf(name: string): string {
  for (const info of ctx.mappings) if (info.name === name) return info.source;
  return "new";
}

function showDocument(file: MappingFile, source: string): void {
  ctx.doc = { name: file.name, patch_type: file.patch_type, summary: file.summary, axes: [] };
  ctx.mods = modsFromFile(file);
  ctx.source = source;
  ctx.selected = null;
  ctx.liveOut.clear();
  ctx.lastSent.clear();
  ctx.pending.clear();
  markSaved();
  renderAll();
  // Because the list is filled before the first mapping arrives, it is pointed at the loaded one here.
  if (sourceOf(file.name) !== "new") select("mapping-list").value = file.name;
}

function renderAll(): void {
  renderPanel();
  renderTouche();
  renderMods();
  renderSelection();
  renderMappingHeader();
}

// Because switching away from a modified mapping would lose the changes, every switch asks first.
async function confirmLeave(): Promise<boolean> {
  if (!isDirty()) return true;
  const answer = await ask(`The mapping "${ctx.doc?.name}" has unsaved changes. Save them before switching?`, ["Save", "Don't save", "Cancel"]);
  if (answer === "Save") return saveDocument(false);
  return answer === "Don't save";
}

async function loadMappingByName(name: string): Promise<void> {
  if (!name) return;
  if (!(await confirmLeave())) {
    if (ctx.doc) select("mapping-list").value = ctx.doc.name;
    return;
  }
  try {
    const file = await getJson<MappingFile>(`/api/mapping?name=${encodeURIComponent(name)}`);
    showDocument(file, sourceOf(name));
    status(`Mapping ${name} loaded.`, "ok");
  } catch (error) {
    status(`The mapping ${name} could not be loaded: ${(error as Error).message}`, "bad");
  }
}

function onMappingLoad(): void {
  loadMappingByName(select("mapping-list").value);
}

async function onMappingNew(): Promise<void> {
  if (!(await confirmLeave())) return;
  const name = await ask("Name of the new mapping (letters, digits, - and _):", ["Create", "Cancel"], "my-mapping");
  if (!name || name === "Cancel") return;
  showDocument({ name: safeName(name), axes: [] }, "new");
  ctx.savedText = ""; // A new mapping counts as unsaved until it is saved once.
  renderMappingHeader();
}

function safeName(name: string): string {
  return name.replace(/[^\p{L}\p{N}_-]/gu, "_");
}

async function refreshMappingList(): Promise<void> {
  const data = await getJson<{ mappings: MappingInfo[] }>("/api/mappings");
  ctx.mappings = data.mappings;
  fillMappingList();
}

async function saveDocument(asNew: boolean): Promise<boolean> {
  if (!ctx.doc) return false;
  let name = ctx.doc.name;
  if (asNew) {
    const answer = await ask("Save this mapping as (letters, digits, - and _):", ["Save", "Cancel"], `${name}-2`);
    if (!answer || answer === "Cancel") return false;
    name = safeName(answer);
    const exists = sourceOf(name) !== "new";
    if (exists && (await ask(`A mapping named "${name}" exists. Replace it?`, ["Replace", "Cancel"])) !== "Replace") return false;
  }
  ctx.doc.name = name;
  try {
    const response = await fetch("/api/mapping", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(fileFromMods()) });
    const body = (await response.json()) as { error?: string; mappings?: MappingInfo[] };
    if (!response.ok || body.error) throw new Error(body.error ?? response.statusText);
    ctx.mappings = body.mappings ?? ctx.mappings;
    ctx.source = sourceOf(name);
    fillMappingList();
    markSaved();
    renderMappingHeader();
    status(`Mapping ${name} saved in library/mappings/${name}.json.`, "ok");
    return true;
  } catch (error) {
    status(`The mapping could not be saved: ${(error as Error).message}`, "bad");
    return false;
  }
}

function onSave(): void {
  saveDocument(false);
}

function onSaveAs(): void {
  saveDocument(true);
}

async function onRevert(): Promise<void> {
  if (!ctx.doc || !isDirty()) return;
  if ((await ask(`Throw away the changes to "${ctx.doc.name}"?`, ["Revert", "Cancel"])) !== "Revert") return;
  if (ctx.source === "new") {
    showDocument({ name: ctx.doc.name, axes: [] }, "new");
    return;
  }
  const file = await getJson<MappingFile>(`/api/mapping?name=${encodeURIComponent(ctx.doc.name)}`);
  showDocument(file, ctx.source);
}

function onMetaChange(): void {
  if (!ctx.doc) return;
  ctx.doc.patch_type = input("mapping-type").value.trim() || undefined;
  ctx.doc.summary = input("mapping-summary").value.trim() || undefined;
  renderMappingHeader();
}

function onBeforeUnload(event: BeforeUnloadEvent): void {
  if (!isDirty()) return;
  event.preventDefault();
}

// ---------- editing modulations ----------

function changed(mod: Mod | undefined, tableToo: boolean): void {
  if (mod) redrawTarget(mod.target);
  if (tableToo) renderMods();
  else if (mod) updateModRowInputs(mod);
  renderSelection();
  renderTouche();
  renderMappingHeader();
}

// The first values of a new modulation: from the keyboard's stored value when it is known, otherwise from the
// bottom, up to the top of the target's range, so that the movement is heard at once.
function addMod(axis: number, targetId: string): void {
  const target = ctx.targets[targetId];
  if (!ctx.doc || !isAvailable(target)) return;
  for (const mod of modsOfTarget(targetId)) {
    if (mod.axis === axis) {
      selectMod(mod.id);
      return;
    }
  }
  const stored = ctx.stored.get(targetId);
  let low = target.low;
  let high = target.high;
  if (stored !== undefined) {
    low = stored;
    high = stored === target.high ? target.low : target.high;
  }
  const mod: Mod = { id: ctx.nextId++, axis, target: targetId, low, high, window: [0, 127], curve: "linear" };
  ctx.mods.push(mod);
  changed(mod, true);
  selectMod(mod.id); // Through selectMod, so that the previously selected control loses its handles.
  status(`${AXIS_NAMES[axis]} now drives ${target.label}. Drag the handles of its ring to set where it starts and ends.`);
}

function removeMod(id: number | null): void {
  const mod = modById(id);
  if (!mod) return;
  ctx.mods.splice(ctx.mods.indexOf(mod), 1);
  ctx.liveOut.delete(mod.id);
  if (ctx.selected === id) ctx.selected = null;
  changed(mod, true);
}

function selectMod(id: number | null): void {
  const previous = modById(ctx.selected);
  ctx.selected = id;
  if (previous) redrawTarget(previous.target);
  const mod = modById(id);
  if (mod) redrawTarget(mod.target);
  for (const row of document.querySelectorAll("#mods-body tr")) {
    (row as HTMLElement).classList.toggle("selected", Number((row as HTMLElement).dataset.mod) === id);
  }
  renderSelection();
}

function onAddModulation(): void {
  for (const id of ctx.targetOrder) {
    if (isAvailable(ctx.targets[id])) {
      addMod(16, id);
      return;
    }
  }
}

// ---------- drag and drop from the Touché onto the keyboard ----------

const DRAG_TYPE = "application/x-touche-axis";

function onSourceDragStart(event: DragEvent): void {
  const source = (event.target as HTMLElement).closest(".source") as HTMLElement | null;
  if (!source || !event.dataTransfer) return;
  event.dataTransfer.setData(DRAG_TYPE, source.dataset.axis ?? "");
  event.dataTransfer.setData("text/plain", `CC${source.dataset.axis}`);
  event.dataTransfer.effectAllowed = "link";
  document.body.classList.add("dragging-source");
}

function onSourceDragEnd(): void {
  document.body.classList.remove("dragging-source");
  for (const dest of document.querySelectorAll(".dest.drop-ok")) dest.classList.remove("drop-ok");
}

function destOf(event: Event): HTMLElement | null {
  return (event.target as HTMLElement).closest(".dest") as HTMLElement | null;
}

function onDestDragOver(event: DragEvent): void {
  const dest = destOf(event);
  if (!dest || !event.dataTransfer || !event.dataTransfer.types.includes(DRAG_TYPE)) return;
  if (!isAvailable(ctx.targets[dest.dataset.target ?? ""])) return;
  event.preventDefault();
  event.dataTransfer.dropEffect = "link";
  dest.classList.add("drop-ok");
}

function onDestDragLeave(event: DragEvent): void {
  const dest = destOf(event);
  if (dest && !dest.contains(event.relatedTarget as Node)) dest.classList.remove("drop-ok");
}

function onDestDrop(event: DragEvent): void {
  const dest = destOf(event);
  if (!dest || !event.dataTransfer) return;
  event.preventDefault();
  dest.classList.remove("drop-ok");
  const axis = Number(event.dataTransfer.getData(DRAG_TYPE));
  if (AXES.includes(axis)) addMod(axis, dest.dataset.target ?? "");
}

// ---------- rings and handles ----------

function valueFromPointer(event: PointerEvent): number {
  const drag = ctx.drag;
  if (!drag) return 0;
  const target = ctx.targets[drag.target];
  const box = drag.svg.getBoundingClientRect();
  let f = 0;
  if (drag.kind === "drawbar") {
    // The drawbar's slot spans 10 to 110 of its 128-unit height.
    const y = ((event.clientY - box.top) / box.height) * 128;
    f = (y - 10) / 100;
  } else {
    const x = event.clientX - (box.left + box.width / 2);
    const y = event.clientY - (box.top + box.height / 2);
    let angle = (Math.atan2(x, -y) * 180) / Math.PI;
    if (angle > 135) angle = 135;
    if (angle < -135) angle = -135;
    f = (angle + 135) / 270;
  }
  f = Math.max(0, Math.min(1, f));
  return Math.round(target.low + f * (target.high - target.low));
}

function onPanelPointerDown(event: PointerEvent): void {
  const element = event.target as Element;
  const handle = element.closest(".handle") as SVGElement | null;
  if (handle) {
    const mod = modById(Number(handle.dataset.mod));
    const svg = handle.closest("svg") as SVGSVGElement | null;
    if (!mod || !svg) return;
    event.preventDefault();
    ctx.drag = { mod: mod.id, end: handle.dataset.end === "low" ? "low" : "high", target: mod.target, kind: svg.dataset.kind === "drawbar" ? "drawbar" : "knob", svg };
    document.body.classList.add("dragging-handle");
    return;
  }
  const ring = element.closest(".ring") as SVGElement | null;
  if (ring) {
    event.preventDefault();
    const id = Number(ring.dataset.mod);
    if (event.altKey) removeMod(id);
    else selectMod(id);
    return;
  }
  if (element.closest(".dest")) selectMod(null);
}

function onPointerMove(event: PointerEvent): void {
  const drag = ctx.drag;
  if (!drag) return;
  const mod = modById(drag.mod);
  if (!mod) return;
  const value = valueFromPointer(event);
  if (mod[drag.end] === value) return;
  mod[drag.end] = value;
  changed(mod, false);
  // Because the handle's element is drawn again, the drag keeps the svg of the widget, which is not replaced.
  drag.svg = document.querySelector(`.dest[data-target="${drag.target}"] svg`) as SVGSVGElement;
  previewMod(mod);
}

function onPointerUp(): void {
  if (!ctx.drag) return;
  ctx.drag = null;
  document.body.classList.remove("dragging-handle");
}

// While a handle is dragged with the bridge live, the keyboard plays the value under the handle, so the start
// and end points can be set by ear.
function previewMod(mod: Mod): void {
  if (!ctx.live || !ctx.drag) return;
  queueValue(ctx.targets[mod.target], mod[ctx.drag.end]);
}

// ---------- modulations table ----------

function rowMod(event: Event): Mod | undefined {
  const row = (event.target as HTMLElement).closest("tr");
  return row ? modById(Number(row.dataset.mod)) : undefined;
}

function onModsChange(event: Event): void {
  const element = event.target as HTMLInputElement;
  const field = element.dataset.field;
  const mod = rowMod(event);
  if (!field || !mod) return;
  const before = mod.target;
  if (field === "axis") mod.axis = Number(element.value);
  else if (field === "target") {
    const target = ctx.targets[element.value];
    mod.target = element.value;
    mod.low = target.low;
    mod.high = target.high;
  } else if (field === "from") mod.window[0] = Math.max(0, Math.min(127, Number(element.value)));
  else if (field === "to") mod.window[1] = Math.max(0, Math.min(127, Number(element.value)));
  else if (field === "low" || field === "high") mod[field] = Number(element.value);
  else if (field === "curve") mod.curve = element.value;
  if (before !== mod.target) redrawTarget(before);
  changed(mod, field === "axis" || field === "target");
  const row = document.querySelector(`#mods-body tr[data-mod="${mod.id}"] .graph`);
  if (row) row.innerHTML = transferSvg(mod);
}

function onModsClick(event: Event): void {
  const element = event.target as HTMLElement;
  const mod = rowMod(event);
  if (!mod) return;
  if (element.dataset.action === "remove") removeMod(mod.id);
  else if (element.tagName !== "INPUT" && element.tagName !== "SELECT") selectMod(mod.id);
}

function onSelectionClick(event: Event): void {
  if ((event.target as HTMLElement).dataset.action === "remove-selected") removeMod(ctx.selected);
}

function onKeyDown(event: KeyboardEvent): void {
  const typing = ["INPUT", "SELECT", "TEXTAREA"].includes((event.target as HTMLElement).tagName);
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    saveDocument(event.shiftKey);
    return;
  }
  if (!typing && (event.key === "Delete" || event.key === "Backspace") && ctx.selected !== null) {
    event.preventDefault();
    removeMod(ctx.selected);
  }
  if (!typing && event.key === "Escape") selectMod(null);
}

// ---------- tabs ----------

function onTab(event: Event): void {
  const tab = (event.target as HTMLElement).closest("[data-tab]") as HTMLElement | null;
  if (!tab) return;
  for (const button of document.querySelectorAll("[data-tab]")) button.classList.toggle("on", button === tab);
  $("view-panel").hidden = tab.dataset.tab !== "panel";
  $("view-mods").hidden = tab.dataset.tab !== "mods";
}

// ---------- live bridge ----------

function messageFor(target: Target, value: number): number[] {
  if (target.kind === "cc") return [0xb0 | ((target.channel ?? 1) - 1), target.cc ?? 0, value];
  return dt1(target.address ?? [0, 0, 0], value);
}

function queueValue(target: Target | undefined, value: number): void {
  if (!target || !isAvailable(target) || ctx.lastSent.get(target.id) === value) return;
  ctx.lastSent.set(target.id, value);
  ctx.pending.set(target.id, messageFor(target, value));
}

// Because a message is queued only when the rounded value changes, and the queue keeps one message per target,
// a fast axis never floods the keyboard: at most one message leaves every few milliseconds.
function drainOne(): void {
  if (!ctx.live || !midi.vr09Out || ctx.pending.size === 0) return;
  const first = ctx.pending.entries().next().value as [string, number[]];
  ctx.pending.delete(first[0]);
  send(first[1]);
  ctx.sentCount++;
  $("sent").textContent = String(ctx.sentCount);
}

function scheduleRedraw(): void {
  if (ctx.redrawScheduled) return;
  ctx.redrawScheduled = true;
  requestAnimationFrame(redrawLive);
}

function redrawLive(): void {
  ctx.redrawScheduled = false;
  for (const id of ctx.redraw) redrawTarget(id);
  ctx.redraw.clear();
  for (const mod of ctx.mods) updateModRowLive(mod);
  for (const axis of AXES) updateMeter(axis);
}

function onToucheData(data: Uint8Array): void {
  if ((data[0] & 0xf0) !== 0xb0) return;
  const cc = data[1];
  const value = data[2];
  if (cc === 80 || cc === 81) {
    $("buttons").textContent = `${cc === 80 ? "left" : "right"} button: ${value}`;
    return;
  }
  if (!AXES.includes(cc)) return;
  ctx.axisValues[cc] = value;
  for (const mod of ctx.mods) {
    if (mod.axis !== cc) continue;
    const out = modValue(mod, value);
    ctx.liveOut.set(mod.id, out);
    ctx.redraw.add(mod.target);
    if (ctx.live) queueValue(ctx.targets[mod.target], out);
  }
  scheduleRedraw();
}

function onLiveToggle(): void {
  ctx.live = input("live").checked;
  ctx.lastSent.clear();
  ctx.pending.clear();
}

// ---------- connection ----------

function portSummary(): string {
  const parts = [`Touché: ${midi.toucheIn?.name ?? "not found"}`, `VR-09 in: ${midi.vr09In?.name ?? "not found"}`, `VR-09 out: ${midi.vr09Out?.name ?? "not found"}`];
  return parts.join(" · ");
}

function onPortsChange(): void {
  applyPorts(portSelects());
  $("port-summary").textContent = portSummary();
}

function onStateChange(): void {
  refreshPorts(portSelects());
  $("port-summary").textContent = portSummary();
}

async function connect(): Promise<boolean> {
  if (midi.access) return true;
  if (!navigator.requestMIDIAccess) {
    status("This browser has no Web MIDI: use Chrome or Edge, on localhost.", "bad");
    return false;
  }
  try {
    await requestAccess();
  } catch (error) {
    status(`MIDI access was refused: ${(error as Error).message}`, "bad");
    return false;
  }
  midi.onTouche = onToucheData;
  const access = midi.access as MIDIAccess | null; // TypeScript keeps the null of the early return above.
  if (access) access.onstatechange = onStateChange;
  refreshPorts(portSelects());
  $("port-summary").textContent = portSummary();
  $("connect").textContent = "Connected";
  status("MIDI connected.", "ok");
  return true;
}

function onConnect(): void {
  connect();
}

// ---------- sounds: a registration or a single tone, independent of the mapping ----------

// After a sound is written, the keyboard's stored values are read back so the knobs and drawbars show them.
async function readStored(): Promise<void> {
  const state = await readBlocks();
  ctx.stored.clear();
  for (const id of ctx.targetOrder) {
    const target = ctx.targets[id];
    if (target.kind !== "dt1" || !target.address) continue;
    const value = state.get(packedAddress(target.address));
    if (value !== undefined) ctx.stored.set(id, value);
  }
  renderPanel();
}

async function writeSound(url: string, label: string): Promise<{ template?: string } | null> {
  if (ctx.busy) return null;
  ctx.busy = true;
  try {
    if (!(await connect())) return null;
    if (!midi.vr09Out) throw new Error("no VR-09 output: check the ports");
    status(`Writing ${label} to the VR-09...`);
    const plan = await getJson<{ messages: number[][]; template?: string }>(url);
    ctx.lastSent.clear();
    ctx.pending.clear();
    await neutralControllers();
    await sendAll(plan.messages, RECALL_GAP_MS);
    await sleep(150);
    await readStored();
    status(`${label} loaded on the keyboard (${plan.messages.length} messages)${midi.vr09In ? "; its stored values are shown on the panel" : ""}.`, "ok");
    return plan;
  } catch (error) {
    status(`${label} could not be loaded: ${(error as Error).message}`, "bad");
    return null;
  } finally {
    ctx.busy = false;
  }
}

async function onLoadRegistration(): Promise<void> {
  const key = select("sound-registration").value;
  if (!key) return;
  const plan = await writeSound(`/api/recall?key=${encodeURIComponent(key)}`, ctx.scenes.titles[key] || key);
  if (plan && input("with-pairing").checked && plan.template) await loadMappingByName(plan.template);
}

async function onLoadTone(): Promise<void> {
  const index = select("sound-tone").value;
  if (index === "") return;
  let name = index;
  for (const tone of ctx.tones) if (String(tone.index) === index) name = tone.name;
  await writeSound(`/api/tone-recall?index=${encodeURIComponent(index)}`, name);
}

async function onReadKeyboard(): Promise<void> {
  if (!(await connect())) return;
  await readStored();
  status(midi.vr09In ? "The keyboard's stored values were read." : "No VR-09 input: the stored values cannot be read.", midi.vr09In ? "ok" : "bad");
}

async function loadSoundLists(): Promise<void> {
  try {
    const pairings = await getJson<{ order: string[]; titles: Record<string, string>; pairings: Record<string, string> }>("/api/pairings");
    ctx.scenes = pairings;
    let html = "";
    for (const key of pairings.order) {
      const paired = pairings.pairings[key] ? ` → ${pairings.pairings[key]}` : "";
      html += `<option value="${escapeHtml(key)}">${escapeHtml(pairings.titles[key] || key)}${escapeHtml(paired)}</option>`;
    }
    select("sound-registration").innerHTML = html;
  } catch (error) {
    status(`The registrations could not be listed: ${(error as Error).message}`, "bad");
  }
  try {
    const data = await getJson<{ tones: { index: number; section: string; group: string | null; name: string }[] }>("/api/tones");
    ctx.tones = data.tones;
    let html = "";
    let group = "";
    for (const tone of data.tones) {
      const label = `${tone.section}${tone.group ? ` · ${tone.group}` : ""}`;
      if (label !== group) {
        html += `${group ? "</optgroup>" : ""}<optgroup label="${escapeHtml(label)}">`;
        group = label;
      }
      html += `<option value="${tone.index}">${escapeHtml(tone.name)}</option>`;
    }
    select("sound-tone").innerHTML = html + (group ? "</optgroup>" : "");
  } catch (error) {
    status(`The tones could not be listed: ${(error as Error).message}`, "bad");
  }
}

// ---------- start ----------

async function loadCatalog(): Promise<void> {
  const targets = await getJson<Target[]>("/maps/targets.json");
  for (const target of targets) {
    ctx.targets[target.id] = target;
    ctx.targetOrder.push(target.id);
  }
}

function listen(id: string, type: string, handler: EventListener): void {
  $(id).addEventListener(type, handler);
}

async function start(): Promise<void> {
  listen("connect", "click", onConnect);
  listen("mapping-load", "click", onMappingLoad);
  listen("mapping-new", "click", onMappingNew as EventListener);
  listen("mapping-save", "click", onSave);
  listen("mapping-save-as", "click", onSaveAs);
  listen("mapping-revert", "click", onRevert as EventListener);
  listen("mapping-type", "input", onMetaChange);
  listen("mapping-summary", "input", onMetaChange);
  listen("load-registration", "click", onLoadRegistration as EventListener);
  listen("load-tone", "click", onLoadTone as EventListener);
  listen("read-keyboard", "click", onReadKeyboard as EventListener);
  listen("live", "change", onLiveToggle);
  listen("add-mod", "click", onAddModulation);
  listen("tabs", "click", onTab);
  listen("sources", "dragstart", onSourceDragStart as EventListener);
  listen("sources", "dragend", onSourceDragEnd);
  listen("keyboard", "dragover", onDestDragOver as EventListener);
  listen("keyboard", "dragleave", onDestDragLeave as EventListener);
  listen("keyboard", "drop", onDestDrop as EventListener);
  listen("keyboard", "pointerdown", onPanelPointerDown as EventListener);
  listen("mods-body", "change", onModsChange);
  listen("mods-body", "click", onModsClick);
  listen("selection", "click", onSelectionClick);
  listen("modal", "click", onModalClick);
  listen("modal", "cancel", onModalCancel);
  listen("modal", "keydown", onModalKey as EventListener);
  for (const id of ["port-touche", "port-vr09-in", "port-vr09-out"]) listen(id, "change", onPortsChange);
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("keydown", onKeyDown);
  window.addEventListener("beforeunload", onBeforeUnload);
  setInterval(drainOne, SEND_GAP_MS);
  try {
    await loadCatalog();
    await refreshMappingList();
  } catch (error) {
    status(`The targets or mappings could not be loaded: ${(error as Error).message}`, "bad");
  }
  const first = new URLSearchParams(location.search).get("mapping") || (ctx.mappings.length ? ctx.mappings[0].name : "");
  if (first) await loadMappingByName(first);
  else renderAll();
  loadSoundLists();
}

start();
