// State of the Touché mapping editor: the VR-09 targets, the layout of the keyboard panel, the mapping being
// edited (as a flat list of modulations) and the arithmetic that turns an axis position into a target value.

export interface Target {
  id: string;
  label: string;
  kind: "dt1" | "cc";
  address?: number[];
  channel?: number;
  cc?: number;
  low: number;
  high: number;
  status: "verified" | "recalled" | "documented" | "unavailable";
  note?: string;
  evidence?: string;
}

// One modulation: one Touché axis driving one target. The file format groups them by axis; the editor keeps
// them flat because the panel, the rings and the table all work per modulation.
export interface Mod {
  id: number;
  axis: number;
  target: string;
  low: number;
  high: number;
  window: [number, number];
  curve: string;
}

export interface MappingFile {
  name: string;
  patch_type?: string;
  summary?: string;
  axes: { axis: number; role?: string; targets: { target: string; low: number; high: number; window: number[]; curve: string }[] }[];
}

export interface MappingInfo {
  name: string;
  source: "template" | "saved" | "saved over a template";
  patch_type: string;
  summary: string;
}

export interface Widget {
  id: string;
  short: string;
  kind: "drawbar" | "knob";
}

export interface Section {
  title: string;
  note: string;
  widgets: Widget[];
}

export const AXES = [16, 17, 18, 19];
export const AXIS_NAMES: Record<number, string> = { 16: "Body", 17: "Tone", 18: "Modulation", 19: "Effects" };
export const AXIS_COLORS: Record<number, string> = { 16: "#f0a33a", 17: "#3fb0e6", 18: "#b98af0", 19: "#56cf8d" };
export const CURVES = ["linear", "soft", "hard"];

const FOOTAGES: [string, string][] = [
  ["16", "16'"], ["5f", "5⅓'"], ["8", "8'"], ["4", "4'"], ["2f", "2⅔'"], ["2", "2'"], ["1f", "1⅗'"], ["1ff", "1⅓'"], ["1", "1'"],
];

function drawbars(manual: string): Widget[] {
  const widgets: Widget[] = [];
  for (const [suffix, short] of FOOTAGES) widgets.push({ id: `organ-${manual}-d${suffix}`, short, kind: "drawbar" });
  return widgets;
}

function knob(id: string, short: string): Widget {
  return { id, short, kind: "knob" };
}

// The panel follows the VR-09's own sections from left to right: organ, rotary, the synth and piano parts, then
// the controllers that only exist as Control Change messages and can only be judged by ear.
export const PANEL: Section[][] = [
  [
    { title: "Upper organ", note: "drawbars", widgets: drawbars("upper") },
    { title: "Lower organ", note: "drawbars", widgets: drawbars("lower") },
    {
      title: "Organ",
      note: "",
      widgets: [
        knob("organ-level", "Level"), knob("overdrive", "Drive"), knob("leakage", "Leakage"), knob("click-on", "Click on"),
        knob("click-off", "Click off"), knob("rotary-fast", "Fast"), knob("eq-high", "EQ high"), knob("eq-low", "EQ low"),
        knob("overdrive-dry", "Dry mix"), knob("rotary-brake", "Brake"),
      ],
    },
  ],
  [
    {
      title: "Rotary",
      note: "",
      widgets: [
        knob("woofer-slow", "Woof slow"), knob("woofer-fast", "Woof fast"), knob("woofer-accel", "Woof accel"),
        knob("tweeter-slow", "Tweet slow"), knob("tweeter-fast", "Tweet fast"), knob("tweeter-accel", "Tweet accel"),
      ],
    },
    {
      title: "Upper synth",
      note: "stored",
      widgets: [
        knob("upper-synth-volume", "Volume"), knob("upper-synth2-volume", "Dual 2"), knob("upper-synth-resonance", "Reso"),
        knob("upper-synth-attack", "Attack"), knob("upper-synth-decay", "Decay"), knob("upper-synth-release", "Release"),
        knob("upper-synth-cutoff", "Cutoff"), knob("upper-synth-portamento", "Porta"),
      ],
    },
    {
      title: "Lower synth",
      note: "stored",
      widgets: [
        knob("lower-synth-volume", "Volume"), knob("lower-synth-resonance", "Reso"), knob("lower-synth-attack", "Attack"),
        knob("lower-synth-decay", "Decay"), knob("lower-synth-release", "Release"), knob("lower-synth-cutoff", "Cutoff"),
        knob("lower-synth-portamento", "Porta"),
      ],
    },
    { title: "Pianos", note: "stored", widgets: [knob("upper-piano-volume", "Upper"), knob("lower-piano-volume", "Lower")] },
  ],
  [
    {
      title: "Upper part",
      note: "CC, channel 4",
      widgets: [
        knob("cc-upper-cutoff", "Cutoff"), knob("cc-upper-resonance", "Reso"), knob("cc-upper-attack", "Attack"),
        knob("cc-upper-decay", "Decay"), knob("cc-upper-release", "Release"), knob("cc-upper-vibrato-depth", "Vib depth"),
        knob("cc-upper-vibrato-rate", "Vib rate"), knob("cc-upper-modulation", "Mod"), knob("cc-upper-expression", "Expr"),
        knob("cc-upper-pan", "Pan"), knob("cc-upper-reverb", "Reverb"), knob("cc-upper-chorus", "Chorus"),
      ],
    },
    {
      title: "Lower part",
      note: "CC, channel 3",
      widgets: [knob("cc-lower-cutoff", "Cutoff"), knob("cc-lower-expression", "Expr"), knob("cc-lower-reverb", "Reverb"), knob("cc-lower-chorus", "Chorus")],
    },
    {
      title: "Piano dual 2",
      note: "CC, channel 1",
      widgets: [knob("cc-piano-expression", "Expr"), knob("cc-piano-reverb", "Reverb"), knob("cc-piano-chorus", "Chorus")],
    },
    {
      title: "Master",
      note: "",
      widgets: [knob("cc-master-expression", "Volume"), knob("rhythm-level", "Rhythm"), knob("song-level", "Song")],
    },
  ],
];

// Because nested functions are not allowed, the state of the page lives in this one object.
export const ctx = {
  targets: {} as Record<string, Target>,
  targetOrder: [] as string[],
  mappings: [] as MappingInfo[],
  doc: null as MappingFile | null,
  mods: [] as Mod[],
  source: "" as string,
  savedText: "",
  nextId: 1,
  selected: null as number | null,
  axisValues: { 16: 0, 17: 0, 18: 0, 19: 0 } as Record<number, number>,
  liveOut: new Map<number, number>(),
  stored: new Map<string, number>(),
  live: true,
  pending: new Map<string, number[]>(),
  lastSent: new Map<string, number>(),
  sentCount: 0,
  redraw: new Set<string>(),
  redrawScheduled: false,
  // A drag either moves the start or end handle of a modulation ("handle"), or sets a control's value on the
  // keyboard ("value"); a knob's value follows the vertical movement from where the drag started.
  drag: null as null | {
    mode: "handle" | "value";
    mod: number;
    end: "low" | "high";
    target: string;
    kind: "knob" | "drawbar";
    svg: SVGSVGElement;
    startY: number;
    startValue: number;
  },
  modalResolve: null as null | ((answer: string) => void),
  busy: false,
  scenes: { order: [] as string[], titles: {} as Record<string, string>, pairings: {} as Record<string, string> },
  tones: [] as { index: number; section: string; group: string | null; name: string }[],
};

// Every placed widget, and then, so that no target of the catalog is lost, the targets the panel does not place.
export function unplacedTargets(): string[] {
  const placed = new Set<string>();
  for (const row of PANEL) for (const section of row) for (const widget of section.widgets) placed.add(widget.id);
  const rest: string[] = [];
  for (const id of ctx.targetOrder) if (!placed.has(id)) rest.push(id);
  return rest;
}

export function modsOfTarget(target: string): Mod[] {
  const found: Mod[] = [];
  for (const mod of ctx.mods) if (mod.target === target) found.push(mod);
  return found;
}

export function modById(id: number | null): Mod | undefined {
  for (const mod of ctx.mods) if (mod.id === id) return mod;
  return undefined;
}

export function isAvailable(target: Target | undefined): boolean {
  return !!target && target.status !== "unavailable";
}

export function curved(x: number, curve: string): number {
  if (curve === "soft") return x * x;
  if (curve === "hard") return Math.sqrt(x);
  return x;
}

export function clamp(value: number, a: number, b: number): number {
  return Math.max(Math.min(a, b), Math.min(Math.max(a, b), value));
}

// The value a modulation sends for an axis position: the window picks the part of the axis travel, the curve
// bends it, and the range (which may descend) scales it to the target's units.
export function modValue(mod: Mod, raw: number): number {
  const target = ctx.targets[mod.target];
  const start = mod.window[0];
  const end = mod.window[1];
  let x = end > start ? (raw - start) / (end - start) : raw >= start ? 1 : 0;
  x = curved(Math.max(0, Math.min(1, x)), mod.curve);
  const value = Math.round(mod.low + x * (mod.high - mod.low));
  return target ? clamp(value, target.low, target.high) : value;
}

// The file format groups the modulations by axis; the editor flattens them on load and groups them on save.
export function modsFromFile(file: MappingFile): Mod[] {
  const mods: Mod[] = [];
  for (const axis of file.axes) {
    for (const t of axis.targets) {
      mods.push({ id: ctx.nextId++, axis: axis.axis, target: t.target, low: t.low, high: t.high, window: [t.window[0], t.window[1]], curve: t.curve || "linear" });
    }
  }
  return mods;
}

export function fileFromMods(): MappingFile {
  const doc = ctx.doc ?? { name: "new-mapping", axes: [] };
  const axes = [];
  for (const axis of AXES) {
    const targets = [];
    for (const mod of ctx.mods) {
      if (mod.axis === axis) targets.push({ target: mod.target, low: mod.low, high: mod.high, window: [mod.window[0], mod.window[1]], curve: mod.curve });
    }
    axes.push({ axis, role: AXIS_NAMES[axis].toLowerCase(), targets });
  }
  return { name: doc.name, patch_type: doc.patch_type, summary: doc.summary, axes };
}

export function isDirty(): boolean {
  return ctx.doc !== null && JSON.stringify(fileFromMods()) !== ctx.savedText;
}

export function markSaved(): void {
  ctx.savedText = JSON.stringify(fileFromMods());
}
