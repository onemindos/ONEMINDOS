// SPDX-License-Identifier: Apache-2.0
import * as Y from 'yjs';
import { addBlock, fork, fromBase64, loadNote, saveNote, sync, toBase64, toMarkdown, type NoteStore } from './noteDoc';

const seed = () => {
  const a = new Y.Doc();
  addBlock(a, { kind: 'heading', level: 1, runs: [{ text: 'Trip' }] });
  addBlock(a, { kind: 'paragraph', runs: [{ text: 'Pack ' }, { text: 'light', marks: ['strong'] }, { text: ' and ' }, { text: 'early', marks: ['em'] }] });
  addBlock(a, { kind: 'bullet', runs: [{ text: 'tent' }] });
  addBlock(a, { kind: 'task', runs: [{ text: 'passport' }], checked: true });
  addBlock(a, { kind: 'task', runs: [{ text: 'charger' }] });
  return a;
};

describe('note as a Yjs document', () => {
  it('exports headings, bold, italic, bullets and checklists as Markdown', () => {
    expect(toMarkdown(seed())).toBe(['# Trip', 'Pack **light** and *early*', '- tent', '- [x] passport', '- [ ] charger'].join('\n'));
  });

  it('keeps both edits when two devices add blocks while offline, in either merge order', () => {
    const a = seed();
    const b = fork(a);
    addBlock(a, { kind: 'task', runs: [{ text: 'from phone A' }] });
    addBlock(b, { kind: 'task', runs: [{ text: 'from phone B' }] });
    const a2 = fork(a);
    const b2 = fork(b);
    sync(a, b);
    Y.applyUpdate(a2, Y.encodeStateAsUpdate(b2));
    Y.applyUpdate(b2, Y.encodeStateAsUpdate(a2));
    const md = toMarkdown(a);
    expect(md).toContain('- [ ] from phone A');
    expect(md).toContain('- [ ] from phone B');
    expect(toMarkdown(b)).toBe(md);
    expect(toMarkdown(a2)).toBe(md);
    expect(toMarkdown(b2)).toBe(md);
  });

  it('merges typing inside one paragraph and a bold change made at the same time', () => {
    const a = seed();
    const b = fork(a);
    const para = (d: Y.Doc) => d.getXmlFragment('prosemirror').get(1) as Y.XmlElement;
    (para(a).get(0) as Y.XmlText).insert(0, 'Note: ');
    const tb = para(b).get(0) as Y.XmlText;
    tb.insert(tb.length, ' (done)');
    tb.format(0, 4, { strong: {} });
    sync(a, b);
    expect(toMarkdown(a)).toBe(toMarkdown(b));
    // No characters lost. Yjs gives text typed at the edge of a formatted run that run's format, so the
    // markers move; the words and the bold on "Pack" stay.
    const md = toMarkdown(a);
    expect(md.split('\n')[1]?.replace(/\*/g, '')).toBe('Note: Pack light and early (done)');
    expect(md).toMatch(/\*\*(Note: )?Pack\*\*/);
  });

  it('converges after several offline rounds and ignores a repeated update', () => {
    const a = seed();
    const b = fork(a);
    for (let i = 0; i < 5; i++) {
      addBlock(a, { kind: 'bullet', runs: [{ text: `a${i}` }] });
      addBlock(b, { kind: 'bullet', runs: [{ text: `b${i}` }] });
    }
    const all = Y.encodeStateAsUpdate(b);
    sync(a, b);
    Y.applyUpdate(a, all);
    const md = toMarkdown(a);
    expect(md.split('\n').filter((l) => /^- [ab]\d$/.test(l))).toHaveLength(10);
    expect(toMarkdown(b)).toBe(md);
  });

  it('keeps a task ticked on one device and a new block added on the other', () => {
    const a = seed();
    const b = fork(a);
    const list = a.getXmlFragment('prosemirror').get(4) as Y.XmlElement;
    (list.get(0) as Y.XmlElement).setAttribute('checked', true as never);
    addBlock(b, { kind: 'paragraph', runs: [{ text: 'end' }] });
    sync(a, b);
    expect(toMarkdown(b)).toContain('- [x] charger');
    expect(toMarkdown(a)).toContain('end');
  });

  it('saves locally and loads the same note back', async () => {
    let held: string | null = null;
    const store: NoteStore = { read: async () => held, write: async (s) => void (held = s) };
    const a = seed();
    expect(await saveNote(store, a)).toBeGreaterThan(0);
    expect(toMarkdown(await loadNote(store))).toBe(toMarkdown(a));
    expect(toMarkdown(await loadNote({ read: async () => null, write: async () => undefined }))).toBe('');
    const bytes = Uint8Array.from([0, 1, 254, 255, 128]);
    expect(Array.from(fromBase64(toBase64(bytes)))).toEqual(Array.from(bytes));
  });
});
