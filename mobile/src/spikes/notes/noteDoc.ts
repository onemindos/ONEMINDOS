// SPDX-License-Identifier: Apache-2.0
// A note is a Yjs document (MIT). Its body is a Y.XmlFragment named "prosemirror" whose shape is exactly what
// y-prosemirror writes for the schema in webEditor.entry.js, so the WebView editor and this code edit one tree.
// Markdown is the open export format (D-032 principle 3); the CRDT is the working copy.
import * as Y from 'yjs';

export const FRAGMENT = 'prosemirror';

export type Mark = 'strong' | 'em';
export type Run = { text: string; marks?: Mark[] };
export type Block =
  | { kind: 'paragraph'; runs: Run[] }
  | { kind: 'heading'; level: 1 | 2 | 3; runs: Run[] }
  | { kind: 'bullet'; runs: Run[] }
  | { kind: 'task'; runs: Run[]; checked?: boolean };

const attrsOf = (marks: Mark[] = []) => Object.fromEntries(marks.map((m) => [m, {}]));

/** Put a text node under `parent` (already in the tree) and fill it with formatted runs. */
function fillText(parent: Y.XmlElement, runs: Run[]): void {
  const t = new Y.XmlText();
  parent.insert(0, [t]);
  let at = 0;
  for (const r of runs) {
    t.insert(at, r.text, attrsOf(r.marks));
    at += r.text.length;
  }
}

/** Append one block (in its own transaction, so it is one update). */
export function addBlock(doc: Y.Doc, block: Block): void {
  const frag = doc.getXmlFragment(FRAGMENT);
  doc.transact(() => {
    if (block.kind === 'paragraph' || block.kind === 'heading') {
      const el = new Y.XmlElement(block.kind);
      if (block.kind === 'heading') el.setAttribute('level', block.level as never);
      frag.push([el]);
      fillText(el, block.runs);
      return;
    }
    const list = new Y.XmlElement(block.kind === 'bullet' ? 'bullet_list' : 'task_list');
    frag.push([list]);
    const item = new Y.XmlElement(block.kind === 'bullet' ? 'list_item' : 'task_item');
    if (block.kind === 'task') item.setAttribute('checked', (block.checked ?? false) as never);
    list.insert(0, [item]);
    const p = new Y.XmlElement('paragraph');
    item.insert(0, [p]);
    fillText(p, block.runs);
  });
}

function inline(t: Y.XmlText): string {
  return t
    .toDelta()
    .map((d: { insert: unknown; attributes?: Record<string, unknown> }) => {
      let s = String(d.insert);
      if (d.attributes?.em) s = `*${s}*`;
      if (d.attributes?.strong) s = `**${s}**`;
      return s;
    })
    .join('');
}

const textOf = (n: Y.XmlElement | Y.XmlText | Y.XmlHook | undefined): string => {
  if (n instanceof Y.XmlText) return inline(n);
  if (n instanceof Y.XmlElement) return n.toArray().map(textOf).join('');
  return '';
};

/** Markdown for the note: headings, **bold**, *italic*, "- " lists and "- [ ]" / "- [x]" checklists. */
export function toMarkdown(doc: Y.Doc): string {
  const out: string[] = [];
  for (const n of doc.getXmlFragment(FRAGMENT).toArray()) {
    if (!(n instanceof Y.XmlElement)) continue;
    if (n.nodeName === 'heading') out.push(`${'#'.repeat(Number(n.getAttribute('level') ?? 1))} ${textOf(n)}`);
    else if (n.nodeName === 'paragraph') out.push(textOf(n));
    else if (n.nodeName === 'bullet_list') for (const li of n.toArray()) out.push(`- ${textOf(li as Y.XmlElement)}`);
    else if (n.nodeName === 'task_list')
      for (const li of n.toArray() as Y.XmlElement[]) out.push(`- [${li.getAttribute('checked') ? 'x' : ' '}] ${textOf(li)}`);
  }
  return out.join('\n');
}

export function toBase64(b: Uint8Array): string {
  let s = '';
  for (let i = 0; i < b.length; i += 0x8000) s += String.fromCharCode(...b.subarray(i, i + 0x8000));
  return btoa(s);
}
export function fromBase64(s: string): Uint8Array {
  const bin = atob(s);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

/** Where the note's bytes live on this device. */
export type NoteStore = { read(): Promise<string | null>; write(b64: string): Promise<void> };

export async function saveNote(store: NoteStore, doc: Y.Doc): Promise<number> {
  const bytes = Y.encodeStateAsUpdate(doc);
  await store.write(toBase64(bytes));
  return bytes.length;
}

export async function loadNote(store: NoteStore): Promise<Y.Doc> {
  const doc = new Y.Doc();
  const raw = await store.read();
  if (raw) Y.applyUpdate(doc, fromBase64(raw));
  return doc;
}

/** Everything `from` has that `into` lacks, both ways. Applying an update twice is harmless. */
export function sync(a: Y.Doc, b: Y.Doc, origin: unknown = 'sync'): void {
  const toB = Y.encodeStateAsUpdate(a, Y.encodeStateVector(b));
  const toA = Y.encodeStateAsUpdate(b, Y.encodeStateVector(a));
  Y.applyUpdate(b, toB, origin);
  Y.applyUpdate(a, toA, origin);
}

export function fork(doc: Y.Doc): Y.Doc {
  const copy = new Y.Doc();
  Y.applyUpdate(copy, Y.encodeStateAsUpdate(doc));
  return copy;
}
