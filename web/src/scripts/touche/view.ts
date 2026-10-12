// Drawing of the mapping editor: the keyboard panel with its rings and drawbar ranges, the Touché sources, and
// the modulations table. Every function returns markup or updates one element; the events are in editor.ts.
import {
  AXES, AXIS_COLORS, AXIS_NAMES, CURVES, PANEL, ctx, isAvailable, modById, modValue, modsOfTarget, unplacedTargets,
  type Mod, type Target, type Widget,
} from "./state";

// A knob sweeps 270 degrees, from 7:30 to 4:30 o'clock; angles are measured clockwise from 12 o'clock.
const KNOB = { size: 70, center: 35, body: 13, firstRing: 18, ringStep: 4.5, start: -135, sweep: 270 };
// A drawbar is a slot whose bar comes out downwards as its value grows, like a Hammond drawbar.
const DRAWBAR = { width: 40, height: 128, slotX: 6, slotWidth: 12, top: 10, length: 100, laneX: 24, laneStep: 5 };
const MAX_RINGS = 3;

export function escapeHtml(text: string): string {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fraction(target: Target, value: number): number {
  if (target.high === target.low) return 0;
  return Math.max(0, Math.min(1, (value - target.low) / (target.high - target.low)));
}

function knobAngle(target: Target, value: number): number {
  return KNOB.start + KNOB.sweep * fraction(target, value);
}

function polar(radius: number, degrees: number): [number, number] {
  const r = (degrees * Math.PI) / 180;
  return [KNOB.center + radius * Math.sin(r), KNOB.center - radius * Math.cos(r)];
}

function arcPath(radius: number, from: number, to: number): string {
  const a = Math.min(from, to);
  const b = Math.max(from, to);
  if (b - a < 0.5) {
    const [x, y] = polar(radius, a);
    return `M ${x.toFixed(2)} ${y.toFixed(2)} L ${x.toFixed(2)} ${y.toFixed(2)}`;
  }
  const [x1, y1] = polar(radius, a);
  const [x2, y2] = polar(radius, b);
  const large = b - a > 180 ? 1 : 0;
  return `M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radius} ${radius} 0 ${large} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}`;
}

// The arrow at the end of a ring points the way the value moves as the axis travels, so a descending range
// (an inverted modulation) shows an arrow turning anticlockwise.
function arrowHead(radius: number, angle: number, clockwise: boolean, color: string): string {
  const [x, y] = polar(radius, angle);
  const tangent = ((angle + (clockwise ? 90 : -90)) * Math.PI) / 180;
  const back = tangent + Math.PI;
  const tipX = x + 3.2 * Math.sin(tangent);
  const tipY = y - 3.2 * Math.cos(tangent);
  const leftX = x + 2.6 * Math.sin(back + 0.9);
  const leftY = y - 2.6 * Math.cos(back + 0.9);
  const rightX = x + 2.6 * Math.sin(back - 0.9);
  const rightY = y - 2.6 * Math.cos(back - 0.9);
  return `<path d="M ${tipX.toFixed(2)} ${tipY.toFixed(2)} L ${leftX.toFixed(2)} ${leftY.toFixed(2)} L ${rightX.toFixed(2)} ${rightY.toFixed(2)} Z" fill="${color}" pointer-events="none"/>`;
}

function ringTitle(mod: Mod, target: Target): string {
  const window = mod.window[0] === 0 && mod.window[1] === 127 ? "whole travel" : `axis ${mod.window[0]} to ${mod.window[1]}`;
  return `${AXIS_NAMES[mod.axis]} (CC${mod.axis}) → ${target.label}: ${mod.low} to ${mod.high}, ${window}, ${mod.curve}`;
}

function knobRing(mod: Mod, target: Target, index: number): string {
  const color = AXIS_COLORS[mod.axis];
  const radius = KNOB.firstRing + index * KNOB.ringStep;
  const from = knobAngle(target, mod.low);
  const to = knobAngle(target, mod.high);
  const selected = ctx.selected === mod.id;
  const width = selected ? 3.6 : 2.6;
  let svg = `<g class="ring${selected ? " selected" : ""}" data-mod="${mod.id}"><title>${escapeHtml(ringTitle(mod, target))}</title>`;
  svg += `<path d="${arcPath(radius, from, to)}" stroke="${color}" stroke-width="${width}" fill="none" stroke-linecap="round" class="ring-arc" data-mod="${mod.id}"/>`;
  svg += arrowHead(radius, to, to >= from, color);
  const live = ctx.liveOut.get(mod.id);
  if (live !== undefined) {
    const [lx, ly] = polar(radius, knobAngle(target, live));
    svg += `<circle cx="${lx.toFixed(2)}" cy="${ly.toFixed(2)}" r="2" fill="#fff" pointer-events="none"/>`;
  }
  if (selected) {
    const [sx, sy] = polar(radius, from);
    const [ex, ey] = polar(radius, to);
    svg += `<circle class="handle" data-mod="${mod.id}" data-end="low" cx="${sx.toFixed(2)}" cy="${sy.toFixed(2)}" r="4" fill="#15171a" stroke="${color}" stroke-width="2"><title>Start: the value at rest (${mod.low})</title></circle>`;
    svg += `<circle class="handle" data-mod="${mod.id}" data-end="high" cx="${ex.toFixed(2)}" cy="${ey.toFixed(2)}" r="4" fill="${color}"><title>End: the value at full travel (${mod.high})</title></circle>`;
  }
  return svg + "</g>";
}

function knobSvg(target: Target): string {
  const mods = modsOfTarget(target.id);
  let svg = `<svg class="knob" viewBox="0 0 ${KNOB.size} ${KNOB.size}" width="${KNOB.size}" height="${KNOB.size}" data-target="${target.id}" data-kind="knob">`;
  svg += `<path d="${arcPath(KNOB.firstRing - 1, KNOB.start, KNOB.start + KNOB.sweep)}" class="track" fill="none"/>`;
  svg += `<circle cx="${KNOB.center}" cy="${KNOB.center}" r="${KNOB.body}" class="body"/>`;
  const stored = ctx.stored.get(target.id);
  if (stored !== undefined) {
    const [px, py] = polar(KNOB.body - 2, knobAngle(target, stored));
    const [qx, qy] = polar(4, knobAngle(target, stored));
    svg += `<line x1="${qx.toFixed(2)}" y1="${qy.toFixed(2)}" x2="${px.toFixed(2)}" y2="${py.toFixed(2)}" class="pointer"><title>Stored value: ${stored}</title></line>`;
  }
  for (let i = 0; i < Math.min(mods.length, MAX_RINGS); i++) svg += knobRing(mods[i], target, i);
  if (mods.length > MAX_RINGS) svg += `<text x="${KNOB.size - 4}" y="10" class="more" text-anchor="end">+${mods.length - MAX_RINGS}</text>`;
  return svg + "</svg>";
}

function drawbarY(target: Target, value: number): number {
  return DRAWBAR.top + DRAWBAR.length * fraction(target, value);
}

// The colours of a Hammond drawbar set: brown for the sub-harmonics, white for the octaves, black for the rest.
function drawbarColor(id: string): string {
  if (id.endsWith("-d16") || id.endsWith("-d5f")) return "#7a4a2a";
  if (id.endsWith("-d2f") || id.endsWith("-d1f") || id.endsWith("-d1ff")) return "#1b1b1b";
  return "#e9e4d8";
}

function drawbarLane(mod: Mod, target: Target, index: number): string {
  const color = AXIS_COLORS[mod.axis];
  const x = DRAWBAR.laneX + index * DRAWBAR.laneStep;
  const y1 = drawbarY(target, mod.low);
  const y2 = drawbarY(target, mod.high);
  const selected = ctx.selected === mod.id;
  let svg = `<g class="ring${selected ? " selected" : ""}" data-mod="${mod.id}"><title>${escapeHtml(ringTitle(mod, target))}</title>`;
  svg += `<line x1="${x}" y1="${y1.toFixed(2)}" x2="${x}" y2="${y2.toFixed(2)}" stroke="${color}" stroke-width="${selected ? 3.6 : 2.6}" stroke-linecap="round" class="ring-arc" data-mod="${mod.id}"/>`;
  const down = y2 >= y1;
  svg += `<path d="M ${x - 2.6} ${(y2 - (down ? 3 : -3)).toFixed(2)} L ${x + 2.6} ${(y2 - (down ? 3 : -3)).toFixed(2)} L ${x} ${(y2 + (down ? 1.5 : -1.5)).toFixed(2)} Z" fill="${color}" pointer-events="none"/>`;
  const live = ctx.liveOut.get(mod.id);
  if (live !== undefined) svg += `<circle cx="${x}" cy="${drawbarY(target, live).toFixed(2)}" r="2" fill="#fff" pointer-events="none"/>`;
  if (selected) {
    svg += `<circle class="handle" data-mod="${mod.id}" data-end="low" cx="${x}" cy="${y1.toFixed(2)}" r="4" fill="#15171a" stroke="${color}" stroke-width="2"><title>Start: the value at rest (${mod.low})</title></circle>`;
    svg += `<circle class="handle" data-mod="${mod.id}" data-end="high" cx="${x}" cy="${y2.toFixed(2)}" r="4" fill="${color}"><title>End: the value at full travel (${mod.high})</title></circle>`;
  }
  return svg + "</g>";
}

function drawbarSvg(target: Target): string {
  const mods = modsOfTarget(target.id);
  let svg = `<svg class="drawbar" viewBox="0 0 ${DRAWBAR.width} ${DRAWBAR.height}" width="${DRAWBAR.width}" height="${DRAWBAR.height}" data-target="${target.id}" data-kind="drawbar">`;
  svg += `<rect x="${DRAWBAR.slotX}" y="${DRAWBAR.top}" width="${DRAWBAR.slotWidth}" height="${DRAWBAR.length}" rx="2" class="slot"/>`;
  for (let step = 0; step <= 8; step++) {
    const y = DRAWBAR.top + (DRAWBAR.length * step) / 8;
    svg += `<line x1="${DRAWBAR.slotX - 3}" y1="${y}" x2="${DRAWBAR.slotX}" y2="${y}" class="tick"/>`;
  }
  const stored = ctx.stored.get(target.id);
  if (stored !== undefined) {
    const y = drawbarY(target, stored);
    svg += `<rect x="${DRAWBAR.slotX + 1}" y="${DRAWBAR.top}" width="${DRAWBAR.slotWidth - 2}" height="${(y - DRAWBAR.top).toFixed(2)}" fill="${drawbarColor(target.id)}" opacity="0.85"><title>Stored value: ${stored}</title></rect>`;
  }
  for (let i = 0; i < Math.min(mods.length, MAX_RINGS); i++) svg += drawbarLane(mods[i], target, i);
  return svg + "</svg>";
}

function statusBadge(target: Target): string {
  if (target.status === "unavailable") return '<span class="badge bad" title="This unit refuses writes to this address">✕</span>';
  if (target.status === "documented") return '<span class="badge" title="A CC: it cannot be read back, judge it by ear">CC</span>';
  return "";
}

export function widgetSvg(target: Target, kind: Widget["kind"]): string {
  return kind === "drawbar" ? drawbarSvg(target) : knobSvg(target);
}

function widgetHtml(widget: Widget): string {
  const target = ctx.targets[widget.id];
  if (!target) return "";
  const classes = ["dest", widget.kind, isAvailable(target) ? "" : "unavailable"].join(" ");
  const title = `${target.label}${target.status === "unavailable" ? " (refused by this unit)" : ""}`;
  return `<div class="${classes}" data-target="${target.id}" data-kind="${widget.kind}" title="${escapeHtml(title)}">
    <div class="art">${widgetSvg(target, widget.kind)}</div>
    <div class="label">${escapeHtml(widget.short)}${statusBadge(target)}</div></div>`;
}

function sectionHtml(title: string, note: string, widgets: Widget[]): string {
  let html = "";
  for (const widget of widgets) html += widgetHtml(widget);
  return `<section class="panel-section"><h3>${escapeHtml(title)}${note ? ` <small>${escapeHtml(note)}</small>` : ""}</h3><div class="widgets">${html}</div></section>`;
}

export function renderPanel(): void {
  let html = "";
  for (const row of PANEL) {
    html += '<div class="panel-row">';
    for (const section of row) html += sectionHtml(section.title, section.note, section.widgets);
    html += "</div>";
  }
  const rest = unplacedTargets();
  if (rest.length) {
    const widgets: Widget[] = [];
    for (const id of rest) widgets.push({ id, short: ctx.targets[id].label, kind: "knob" });
    html += `<div class="panel-row">${sectionHtml("Other targets", "", widgets)}</div>`;
  }
  (document.getElementById("keyboard") as HTMLElement).innerHTML = html;
}

// Only the widgets whose modulations or values changed are drawn again.
export function redrawTarget(id: string): void {
  const holder = document.querySelector(`.dest[data-target="${id}"] .art`);
  const target = ctx.targets[id];
  if (!holder || !target) return;
  const kind = (holder.parentElement as HTMLElement).dataset.kind === "drawbar" ? "drawbar" : "knob";
  holder.innerHTML = widgetSvg(target, kind);
}

// ---------- Touché ----------

export function renderTouche(): void {
  let html = "";
  for (const axis of AXES) {
    let count = 0;
    for (const mod of ctx.mods) if (mod.axis === axis) count++;
    html += `<div class="source" draggable="true" data-axis="${axis}" style="--axis-color:${AXIS_COLORS[axis]}" title="Drag onto a keyboard control to modulate it with this axis">
      <div class="source-head"><span class="dot"></span><b>${AXIS_NAMES[axis]}</b><small>CC${axis}</small><span class="count">${count || ""}</span></div>
      <div class="meter"><div class="fill" id="meter-${axis}"></div></div></div>`;
  }
  (document.getElementById("sources") as HTMLElement).innerHTML = html;
  for (const axis of AXES) updateMeter(axis);
}

export function updateMeter(axis: number): void {
  const fill = document.getElementById(`meter-${axis}`);
  if (fill) fill.style.width = `${(ctx.axisValues[axis] / 127) * 100}%`;
}

// ---------- modulations table ----------

function targetOptions(selected: string): string {
  const groups: [string, string][] = [["verified", "Verified on the unit"], ["recalled", "Changes with a recall"], ["documented", "CC, judge by ear"], ["unavailable", "Refused by this unit"]];
  let html = "";
  for (const [status, label] of groups) {
    html += `<optgroup label="${label}">`;
    for (const id of ctx.targetOrder) {
      const target = ctx.targets[id];
      if (target.status === status) html += `<option value="${id}" ${id === selected ? "selected" : ""}>${escapeHtml(target.label)}</option>`;
    }
    html += "</optgroup>";
  }
  return html;
}

function axisOptions(selected: number): string {
  let html = "";
  for (const axis of AXES) html += `<option value="${axis}" ${axis === selected ? "selected" : ""}>CC${axis} ${AXIS_NAMES[axis]}</option>`;
  return html;
}

function curveOptions(selected: string): string {
  let html = "";
  for (const curve of CURVES) html += `<option ${curve === selected ? "selected" : ""}>${curve}</option>`;
  return html;
}

// The transfer graph: the axis travel on x, the target's range on y, with the window and the curve.
export function transferSvg(mod: Mod): string {
  const target = ctx.targets[mod.target];
  if (!target) return "";
  const width = 96;
  const height = 34;
  const points: string[] = [];
  for (let i = 0; i <= 48; i++) {
    const raw = (127 * i) / 48;
    const y = height - 2 - (height - 4) * fraction(target, modValue(mod, raw));
    points.push(`${((width * i) / 48).toFixed(1)},${y.toFixed(1)}`);
  }
  const live = ctx.axisValues[mod.axis];
  const liveX = (width * live) / 127;
  return `<svg class="transfer" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
    <rect x="${(width * mod.window[0]) / 127}" y="0" width="${(width * Math.max(0, mod.window[1] - mod.window[0])) / 127}" height="${height}" class="window"/>
    <polyline points="${points.join(" ")}" fill="none" stroke="${AXIS_COLORS[mod.axis]}" stroke-width="2"/>
    <line x1="${liveX}" y1="0" x2="${liveX}" y2="${height}" class="live"/></svg>`;
}

function modRowHtml(mod: Mod): string {
  const target = ctx.targets[mod.target];
  const live = ctx.liveOut.get(mod.id);
  const warn = target && !isAvailable(target) ? ' <span class="badge bad" title="This unit refuses writes to this address">✕</span>' : "";
  return `<tr data-mod="${mod.id}" class="${ctx.selected === mod.id ? "selected" : ""}" style="--axis-color:${AXIS_COLORS[mod.axis]}">
    <td><span class="dot"></span><select data-field="axis">${axisOptions(mod.axis)}</select></td>
    <td><select data-field="target">${targetOptions(mod.target)}</select>${warn}</td>
    <td><input data-field="low" type="number" value="${mod.low}"></td>
    <td><input data-field="high" type="number" value="${mod.high}"></td>
    <td><input data-field="from" type="number" min="0" max="127" value="${mod.window[0]}"></td>
    <td><input data-field="to" type="number" min="0" max="127" value="${mod.window[1]}"></td>
    <td><select data-field="curve">${curveOptions(mod.curve)}</select></td>
    <td class="graph">${transferSvg(mod)}</td>
    <td class="live-value">${live === undefined ? "" : live}</td>
    <td><button data-action="remove" title="Remove this modulation">✕</button></td></tr>`;
}

export function renderMods(): void {
  const body = document.getElementById("mods-body") as HTMLElement;
  if (!ctx.mods.length) {
    body.innerHTML = '<tr><td colspan="10" class="empty">No modulation yet: drag a Touché axis onto a keyboard control in the Panel tab, or press "Add modulation".</td></tr>';
    return;
  }
  let html = "";
  for (const axis of AXES) for (const mod of ctx.mods) if (mod.axis === axis) html += modRowHtml(mod);
  body.innerHTML = html;
}

// While an axis moves, only the live cells of the table change, so the inputs keep their focus.
export function updateModRowLive(mod: Mod): void {
  const row = document.querySelector(`#mods-body tr[data-mod="${mod.id}"]`);
  if (!row) return;
  const cell = row.querySelector(".live-value");
  const graph = row.querySelector(".graph");
  const live = ctx.liveOut.get(mod.id);
  if (cell) cell.textContent = live === undefined ? "" : String(live);
  if (graph) graph.innerHTML = transferSvg(mod);
}

export function updateModRowInputs(mod: Mod): void {
  const row = document.querySelector(`#mods-body tr[data-mod="${mod.id}"]`);
  if (!row) return;
  const low = row.querySelector('[data-field="low"]') as HTMLInputElement | null;
  const high = row.querySelector('[data-field="high"]') as HTMLInputElement | null;
  if (low) low.value = String(mod.low);
  if (high) high.value = String(mod.high);
  updateModRowLive(mod);
}

export function renderSelection(): void {
  const mod = modById(ctx.selected);
  const box = document.getElementById("selection") as HTMLElement;
  if (!mod) {
    box.innerHTML = '<span class="muted">Click a ring to select a modulation, then drag its start (hollow) or end (filled) handle. Delete removes it.</span>';
    return;
  }
  const target = ctx.targets[mod.target];
  box.innerHTML = `<span class="dot" style="--axis-color:${AXIS_COLORS[mod.axis]}"></span> <b>${AXIS_NAMES[mod.axis]}</b> → ${escapeHtml(target ? target.label : mod.target)}:
    from <b>${mod.low}</b> at rest to <b>${mod.high}</b> at full travel${mod.low > mod.high ? " (inverted)" : ""},
    ${mod.window[0] === 0 && mod.window[1] === 127 ? "over the whole travel" : `over axis ${mod.window[0]}–${mod.window[1]}`}, ${mod.curve} curve.
    <button data-action="remove-selected">Remove</button>`;
}
