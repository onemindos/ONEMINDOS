// SPDX-License-Identifier: Apache-2.0
// Runs inside the WebView only. Bundled offline by scripts/build-notes-editor.mjs; it never loads a network page.
// ProseMirror (MIT) draws and edits the note; y-prosemirror binds it to a Yjs doc (MIT). Updates go to the app
// as base64 messages; the app owns saving and merging.
import { Schema } from 'prosemirror-model';
import { schema as basic } from 'prosemirror-schema-basic';
import { addListNodes, wrapInList, liftListItem, sinkListItem, splitListItem } from 'prosemirror-schema-list';
import { EditorState } from 'prosemirror-state';
import { EditorView } from 'prosemirror-view';
import { keymap } from 'prosemirror-keymap';
import { baseKeymap, setBlockType, toggleMark } from 'prosemirror-commands';
import { ySyncPlugin, yUndoPlugin, undo, redo } from 'y-prosemirror';
import * as Y from 'yjs';

const nodes = addListNodes(basic.spec.nodes, 'paragraph block*', 'block')
  .addToEnd('task_list', { group: 'block', content: 'task_item+', parseDOM: [{ tag: 'ul[data-tasks]' }], toDOM: () => ['ul', { 'data-tasks': '1' }, 0] })
  .addToEnd('task_item', {
    content: 'paragraph block*',
    defining: true,
    attrs: { checked: { default: false } },
    parseDOM: [{ tag: 'li[data-task]', getAttrs: (d) => ({ checked: d.getAttribute('data-checked') === '1' }) }],
    toDOM: (n) => ['li', { 'data-task': '1', 'data-checked': n.attrs.checked ? '1' : '0' }, 0],
  });
const schema = new Schema({ nodes, marks: basic.spec.marks });

const b64 = (u) => { let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); };
const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
const post = (m) => window.ReactNativeWebView.postMessage(JSON.stringify(m));

const ydoc = new Y.Doc();
ydoc.on('update', (u, origin) => { if (origin !== 'app') post({ type: 'update', u: b64(u) }); });
let view;

const cmds = {
  bold: toggleMark(schema.marks.strong),
  italic: toggleMark(schema.marks.em),
  h1: (s, d) => (s.selection.$from.parent.type === schema.nodes.heading ? setBlockType(schema.nodes.paragraph) : setBlockType(schema.nodes.heading, { level: 1 }))(s, d),
  h2: (s, d) => (s.selection.$from.parent.type === schema.nodes.heading ? setBlockType(schema.nodes.paragraph) : setBlockType(schema.nodes.heading, { level: 2 }))(s, d),
  bullet: wrapInList(schema.nodes.bullet_list),
  task: wrapInList(schema.nodes.task_list),
  done: (s, d) => {
    const $f = s.selection.$from;
    for (let depth = $f.depth; depth > 0; depth--) {
      const n = $f.node(depth);
      if (n.type === schema.nodes.task_item) { if (d) d(s.tr.setNodeMarkup($f.before(depth), null, { checked: !n.attrs.checked })); return true; }
    }
    return false;
  },
  undo, redo,
};

function start() {
  view = new EditorView(document.getElementById('editor'), {
    state: EditorState.create({
      schema,
      plugins: [
        ySyncPlugin(ydoc.getXmlFragment('prosemirror')),
        yUndoPlugin(),
        keymap({ 'Mod-b': cmds.bold, 'Mod-i': cmds.italic, 'Mod-z': undo, 'Mod-y': redo, Enter: splitListItem(schema.nodes.list_item), Tab: sinkListItem(schema.nodes.list_item), 'Shift-Tab': liftListItem(schema.nodes.list_item) }),
        keymap(baseKeymap),
      ],
    }),
    handleClickOn(v, pos, node, nodePos, event) {
      if (node.type === schema.nodes.task_item && event.offsetX < 30) { v.dispatch(v.state.tr.setNodeMarkup(nodePos, null, { checked: !node.attrs.checked })); return true; }
      return false;
    },
  });
}

window.__om = (m) => {
  if (m.type === 'init') { Y.applyUpdate(ydoc, unb64(m.state), 'app'); if (!view) start(); }
  else if (m.type === 'remote') Y.applyUpdate(ydoc, unb64(m.u), 'app');
  else if (m.type === 'cmd' && view && cmds[m.name]) { cmds[m.name](view.state, view.dispatch, view); view.focus(); }
};
document.querySelectorAll('[data-cmd]').forEach((b) => {
  b.addEventListener('mousedown', (e) => e.preventDefault());
  b.addEventListener('click', () => window.__om({ type: 'cmd', name: b.getAttribute('data-cmd') }));
});
post({ type: 'ready' });
