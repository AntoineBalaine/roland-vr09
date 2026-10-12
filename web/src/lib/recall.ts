// Turns a library patch into the DT1 messages that make the VR-09 sound like it: the same plan as
// `vr09.py recall`. The values of the patch are written at every address that differs between any two
// patches of the library, so the result does not depend on what was loaded before.
interface Block {
  name: string;
  start: number[]; // the first address, 7 bits per byte
  kind: "kb" | "synth"; // keyboard part (model 62, 3-byte addresses) or synth section (model 00 00 71, 4-byte addresses)
}

// The blocks of a dump, in the order of vr09.py.
const BLOCKS: Block[] = [
  { name: "system", start: [0x00, 0x00, 0x00], kind: "kb" },
  { name: "upper_piano", start: [0x01, 0x01, 0x00], kind: "kb" },
  { name: "upper_synth_dual2", start: [0x01, 0x02, 0x00], kind: "kb" },
  { name: "upper_synth", start: [0x01, 0x03, 0x00], kind: "kb" },
  { name: "lower_piano", start: [0x01, 0x11, 0x00], kind: "kb" },
  { name: "lower_synth", start: [0x01, 0x13, 0x00], kind: "kb" },
  { name: "upper_piano_dual2", start: [0x01, 0x31, 0x00], kind: "kb" },
  { name: "drum", start: [0x01, 0x41, 0x00], kind: "kb" },
  { name: "part_01_00", start: [0x01, 0x00, 0x00], kind: "kb" },
  { name: "part_01_10", start: [0x01, 0x10, 0x00], kind: "kb" },
  { name: "part_01_12", start: [0x01, 0x12, 0x00], kind: "kb" },
  { name: "part_01_20", start: [0x01, 0x20, 0x00], kind: "kb" },
  { name: "part_01_21", start: [0x01, 0x21, 0x00], kind: "kb" },
  { name: "part_01_22", start: [0x01, 0x22, 0x00], kind: "kb" },
  { name: "part_01_30", start: [0x01, 0x30, 0x00], kind: "kb" },
  { name: "part_01_51", start: [0x01, 0x51, 0x00], kind: "kb" },
  { name: "organ_upper", start: [0x02, 0x00, 0x00], kind: "kb" },
  { name: "organ_lower", start: [0x02, 0x01, 0x00], kind: "kb" },
  { name: "organ_pedal", start: [0x02, 0x02, 0x00], kind: "kb" },
  { name: "synth_set_upper2", start: [0x18, 0x00, 0x21, 0x00], kind: "synth" },
  { name: "synth_set_upper1", start: [0x18, 0x00, 0x22, 0x00], kind: "synth" },
  { name: "synth_set_lower", start: [0x18, 0x00, 0x25, 0x00], kind: "synth" },
];

export type Dump = Record<string, number>;

const pack = (bytes: number[]): number => bytes.reduce((value, b) => (value << 7) | b, 0);
const unpack = (value: number, length: number): number[] => Array.from({ length }, (_, i) => (value >> (7 * (length - 1 - i))) & 0x7f);
const checksum = (data: number[]): number => (128 - (data.reduce((sum, b) => sum + b, 0) % 128)) % 128;
const keyOf = (block: string, address: number): string => `${block}:${address.toString(16).toUpperCase().padStart(8, "0")}`;

// The keys whose value is not the same in every dump.
function varyingKeys(dumps: Dump[]): string[] {
  const keys = new Set<string>();
  for (const d of dumps) for (const k of Object.keys(d)) keys.add(k);
  return [...keys].filter((k) => new Set(dumps.map((d) => d[k])).size > 1).sort();
}

// A DT1 must start at a parameter's own address, so a few parameters travel together (as in vr09.groups):
// the reverb type with its level, the tone number with its two bank bytes, and the same for the synth set parts.
function groupsOf(changed: string[]): { block: string; start: number; length: number }[] {
  const base = new Map(BLOCKS.map((b) => [b.name, pack(b.start)]));
  const found = new Map<string, { block: string; start: number; length: number }>();
  for (const key of changed) {
    const [block, hex] = key.split(":");
    const address = parseInt(hex, 16);
    const offset = address - (base.get(block) ?? 0);
    let group = { block, start: address, length: 1 };
    if (block === "system" && (offset === 0 || offset === 1)) group = { block, start: base.get(block)!, length: 2 };
    else if (/^(upper_|lower_|drum|part_)/.test(block) && offset >= 1 && offset <= 3) group = { block, start: base.get(block)! + 1, length: 3 };
    else if (block.startsWith("synth_set") && offset >= 6 && offset <= 8) group = { block, start: base.get(block)! + 6, length: 3 };
    found.set(`${group.block}|${group.start}|${group.length}`, group);
  }
  return [...found.values()].sort((a, b) => (a.block < b.block ? -1 : a.block > b.block ? 1 : a.start - b.start || a.length - b.length));
}

// The complete SysEx messages that put the patch's values at every address that varies among the dumps.
export function recallMessages(dumps: Record<string, Dump>, key: string): number[][] {
  const target = dumps[key];
  if (!target) throw new Error(`no dump for '${key}'`);
  const kindOf = new Map(BLOCKS.map((b) => [b.name, b.kind]));
  return groupsOf(varyingKeys(Object.values(dumps))).map((g) => {
    const data = Array.from({ length: g.length }, (_, i) => target[keyOf(g.block, g.start + i)] ?? 0);
    const synth = kindOf.get(g.block) === "synth";
    const body = [...unpack(g.start, synth ? 4 : 3), ...data];
    const header = synth ? [0xf0, 0x41, 0x10, 0x00, 0x00, 0x71, 0x12] : [0xf0, 0x41, 0x10, 0x62, 0x12];
    return [...header, ...body, checksum(body), 0xf7];
  });
}

// One DT1 message to the keyboard part (model 62), from the first address and the bytes to write there.
export function dt1Message(address: number[], data: number[]): number[] {
  const body = [...address, ...data];
  return [0xf0, 0x41, 0x10, 0x62, 0x12, ...body, checksum(body), 0xf7];
}
