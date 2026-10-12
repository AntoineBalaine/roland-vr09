// MIDI side of the mapping editor: the ports, the paced sending to the VR-09, the recall of a registration or a
// single tone, and the reading of the keyboard's stored values with RQ1.

export const RECALL_GAP_MS = 3; // The gap between the messages of a recall; 2 ms worked in every test with vr09.py.
export const SEND_GAP_MS = 5; // The unit overflows its buffer with no gap, and gaps of 1 to 20 ms all worked.

// Because the controllers a mapping moves are not part of a registration, every load first puts them back at
// rest: without this, a CC left low by a mapping kept the keyboard almost mute after a switch.
const NEUTRAL_CHANNELS = [1, 3, 4, 16];
const NEUTRAL_VALUES = [[121, 0], [11, 127], [1, 0], [10, 64], [71, 64], [72, 64], [73, 64], [74, 64], [75, 64], [76, 64], [77, 64]];

// The blocks that hold every DT1 target of the catalog, with the addresses and sizes that vr09.py uses.
export const READ_BLOCKS = [
  { address: [0x00, 0x00, 0x00], size: 0x69 },
  { address: [0x02, 0x00, 0x00], size: 0x3a },
  { address: [0x02, 0x01, 0x00], size: 0x3a },
  { address: [0x01, 0x01, 0x00], size: 0x65 },
  { address: [0x01, 0x02, 0x00], size: 0x65 },
  { address: [0x01, 0x03, 0x00], size: 0x65 },
  { address: [0x01, 0x11, 0x00], size: 0x65 },
  { address: [0x01, 0x13, 0x00], size: 0x65 },
];

export const midi = {
  access: null as MIDIAccess | null,
  toucheIn: null as MIDIInput | null,
  vr09In: null as MIDIInput | null,
  vr09Out: null as MIDIOutput | null,
  collect: null as Map<number, number> | null,
  onTouche: null as null | ((data: Uint8Array) => void),
};

export function checksum(bytes: number[]): number {
  let sum = 0;
  for (const b of bytes) sum += b;
  return (128 - (sum % 128)) % 128;
}

export function dt1(address: number[], value: number): number[] {
  const body = [...address, value];
  return [0xf0, 0x41, 0x10, 0x62, 0x12, ...body, checksum(body), 0xf7];
}

export function rq1(address: number[], size: number): number[] {
  const body = [...address, (size >> 14) & 0x7f, (size >> 7) & 0x7f, size & 0x7f];
  return [0xf0, 0x41, 0x10, 0x62, 0x11, ...body, checksum(body), 0xf7];
}

export function packedAddress(bytes: ArrayLike<number>): number {
  return (bytes[0] << 14) | (bytes[1] << 7) | bytes[2];
}

function startTimer(ms: number, resolve: () => void): void {
  setTimeout(resolve, ms);
}

export function sleep(ms: number): Promise<void> {
  return new Promise<void>(startTimer.bind(null, ms));
}

// ---------- ports ----------

function storeDt1(data: Uint8Array): void {
  const isDt1 = data[0] === 0xf0 && data[1] === 0x41 && data[3] === 0x62 && data[4] === 0x12;
  if (!isDt1 || !midi.collect) return;
  const base = packedAddress(data.subarray(5, 8));
  const values = data.subarray(8, data.length - 2);
  for (let i = 0; i < values.length; i++) midi.collect.set(base + i, values[i]);
}

function onMidiMessage(event: Event): void {
  const message = event as MIDIMessageEvent;
  const data = message.data;
  if (!data) return;
  const port = message.target as MIDIInput;
  if (midi.toucheIn && port.id === midi.toucheIn.id && midi.onTouche) midi.onTouche(data);
  if (midi.vr09In && port.id === midi.vr09In.id && data[0] < 0xf8) storeDt1(data);
}

function fillSelect(select: HTMLSelectElement, ports: Map<string, MIDIPort>, hints: string[]): void {
  const previous = select.value;
  let html = '<option value="">(none)</option>';
  let match = "";
  for (const port of ports.values()) {
    html += `<option value="${port.id}">${port.name}</option>`;
    for (const hint of hints) if (!match && (port.name ?? "").toLowerCase().includes(hint)) match = port.id;
  }
  select.innerHTML = html;
  select.value = previous && ports.has(previous) ? previous : match;
}

function chooseInput(select: HTMLSelectElement, previous: MIDIInput | null): MIDIInput | null {
  if (previous) previous.removeEventListener("midimessage", onMidiMessage);
  const port = (midi.access?.inputs.get(select.value) as MIDIInput | undefined) ?? null;
  if (port) port.addEventListener("midimessage", onMidiMessage);
  return port;
}

export function applyPorts(selects: { touche: HTMLSelectElement; vr09In: HTMLSelectElement; vr09Out: HTMLSelectElement }): void {
  if (!midi.access) return;
  midi.toucheIn = chooseInput(selects.touche, midi.toucheIn);
  midi.vr09In = chooseInput(selects.vr09In, midi.vr09In);
  midi.vr09Out = (midi.access.outputs.get(selects.vr09Out.value) as MIDIOutput | undefined) ?? null;
}

export function refreshPorts(selects: { touche: HTMLSelectElement; vr09In: HTMLSelectElement; vr09Out: HTMLSelectElement }): void {
  if (!midi.access) return;
  // The Touché's performance CCs arrive on its "Main Port"; its "Control Port" carries Lié's SysEx.
  fillSelect(selects.touche, midi.access.inputs as unknown as Map<string, MIDIPort>, ["main port", "touche"]);
  fillSelect(selects.vr09In, midi.access.inputs as unknown as Map<string, MIDIPort>, ["vr-09"]);
  fillSelect(selects.vr09Out, midi.access.outputs as unknown as Map<string, MIDIPort>, ["vr-09"]);
  applyPorts(selects);
}

export async function requestAccess(): Promise<void> {
  midi.access = await navigator.requestMIDIAccess({ sysex: true });
}

// ---------- sending ----------

export function send(message: number[]): void {
  if (midi.vr09Out) midi.vr09Out.send(message);
}

export async function sendAll(messages: number[][], gap: number): Promise<void> {
  for (const message of messages) {
    send(message);
    await sleep(gap);
  }
}

export async function neutralControllers(): Promise<void> {
  for (const channel of NEUTRAL_CHANNELS) {
    for (const pair of NEUTRAL_VALUES) {
      send([0xb0 | (channel - 1), pair[0], pair[1]]);
      await sleep(2);
    }
  }
}

// One parameter read back after a write, to tell whether the keyboard kept the value; undefined when nothing
// answered (no VR-09 input, or the unit was busy).
export async function readOne(address: number[]): Promise<number | undefined> {
  if (!midi.vr09Out || !midi.vr09In) return undefined;
  const state = new Map<number, number>();
  midi.collect = state;
  send(rq1(address, 1));
  await sleep(250);
  midi.collect = null;
  return state.get(packedAddress(address));
}

// Because the unit answers each RQ1 with one or more DT1 messages, a short wait after every request lets the
// replies arrive; they are collected by address, 7 bits per byte packed into one number.
export async function readBlocks(): Promise<Map<number, number>> {
  const state = new Map<number, number>();
  if (!midi.vr09Out || !midi.vr09In) return state;
  midi.collect = state;
  for (const block of READ_BLOCKS) {
    send(rq1(block.address, block.size));
    await sleep(120);
  }
  await sleep(150);
  midi.collect = null;
  return state;
}
