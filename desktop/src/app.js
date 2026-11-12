// SPDX-License-Identifier: Apache-2.0
// Tray popover. Every call goes to a Rust command; this page has no network, file or shell
// permission of its own (see src-tauri/capabilities/default.json). Text from the box is
// only ever set with textContent, never parsed as HTML.

import { ago, approvalsTile, backupsTile, errorText, isInsecureAddress, nodesTile, updatesTile } from './format.js';

const tauri = window.__TAURI__;
const invoke = (cmd, args) => tauri.core.invoke(cmd, args);
const $ = (id) => document.getElementById(id);
const view = $('view');

let mode = 'home'; // home | add
let boxes = [];
let found = [];
let searching = false;
let pairing = { url: '', token: '', insecure: false, error: '', busy: false };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else if (k === 'text') el.textContent = v;
    else if (k === 'style') el.style.cssText = v; // CSSOM: allowed under style-src 'self'
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid);
  return el;
}

const ICON = {
  globe: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM3 12h18M12 3c2.5 2.7 2.5 15.3 0 18M12 3c-2.5 2.7-2.5 15.3 0 18',
  folder: 'M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z',
  search: 'M11 4a7 7 0 1 0 0 14 7 7 0 0 0 0-14zM20 20l-4-4',
};
function icon(name) {
  const ns = 'http://www.w3.org/2000/svg';
  const svg = document.createElementNS(ns, 'svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  const p = document.createElementNS(ns, 'path');
  p.setAttribute('d', ICON[name]);
  svg.append(p);
  return svg;
}

function tile(t) {
  return h('div', { class: `tile ${t.tone}` }, h('div', { class: 'v', text: t.value }), h('div', { class: 'l', text: t.label }), t.detail ? h('div', { class: 'd', text: t.detail }) : null);
}

function boxCard(b) {
  const st = b.status;
  const online = st && st.reachable;
  const sub = h(
    'div',
    { class: 'box-sub' },
    h('span', { class: `dot ${st ? (online ? 'ok' : 'bad') : ''}` }),
    h('span', { text: !st ? 'Checking…' : online ? `Online${st.version ? ` · v${st.version}` : ''}` : 'Not reachable' }),
    b.insecure ? h('span', { class: 'badge warn', title: 'This box is paired over plain HTTP.', text: 'Not encrypted' }) : null,
  );
  const card = h('section', { class: 'card' }, h('div', { class: 'box-head' }, h('div', {}, h('div', { class: 'box-name', text: (st && st.name) || b.name }), sub)));

  if (st && !online) card.append(h('div', { class: 'error', style: 'margin-top:12px', text: errorText(st.error) }));
  if (st && online) {
    card.append(h('div', { class: 'tiles' }, tile(nodesTile(st)), tile(approvalsTile(st)), tile(updatesTile(st)), tile(backupsTile(st))));
    if (st.pending.length) {
      card.append(
        h('div', { class: 'section-title', text: 'Waiting for your approval' }),
        h(
          'div',
          { class: 'pending' },
          st.pending.slice(0, 4).map((p) =>
            h(
              'div',
              { class: 'pending-item' },
              h('div', {}, h('div', { class: 'what', text: p.target ? `${p.kind} · ${p.target}` : p.kind }), h('div', { class: 'who', text: `asked by ${p.requested_by || 'someone'}` })),
              h('button', { class: 'btn small', text: 'Review', onclick: () => run('open_dashboard', { id: b.id }) }),
            ),
          ),
        ),
        h('div', { class: 'note', style: 'margin-top:6px', text: 'You approve in the dashboard. A notification never approves anything.' }),
      );
    }
  }
  card.append(
    h(
      'div',
      { class: 'actions' },
      h('button', { class: 'btn primary', onclick: () => run('open_dashboard', { id: b.id }) }, icon('globe'), 'Open dashboard'),
      h('button', { class: 'btn', title: "Opens the box's file share in your file manager", onclick: () => run('open_files', { id: b.id }) }, icon('folder'), 'Files'),
    ),
  );
  card.append(
    h(
      'div',
      { class: 'box-sub', style: 'margin-top:10px;justify-content:space-between' },
      h('span', { text: st ? `Checked ${ago(st.fetched_at)}` : '' }),
      h('button', {
        class: 'link small',
        text: 'Remove',
        title: 'Forget this box and delete its token from the keychain',
        onclick: async (ev) => {
          // Two clicks: the first arms, the second removes.
          if (!ev.currentTarget.dataset.armed) {
            ev.currentTarget.dataset.armed = '1';
            ev.currentTarget.textContent = 'Click again to remove';
            return;
          }
          await run('remove_box', { id: b.id });
          await load();
        },
      }),
    ),
  );
  return card;
}

function homeView() {
  if (!boxes.length) return addView(true);
  return boxes.map(boxCard);
}

function addView(first = false) {
  const nodes = [];
  nodes.push(
    h(
      'div',
      { class: 'hero' },
      h('div', { class: `radar ${searching ? 'searching' : ''}` }, icon('search')),
      h('h1', { text: first ? 'Find your OneMind box' : 'Add a box' }),
      h('p', { text: searching ? 'Looking on your network…' : found.length ? 'Pick your box, then paste its token.' : 'No box found yet. Type its address below.' }),
    ),
  );
  if (found.length) {
    nodes.push(
      h(
        'div',
        { class: 'found' },
        found.map((f) =>
          h(
            'button',
            {
              class: `found-item ${pairing.url === f.url ? 'sel' : ''}`,
              onclick: () => {
                pairing.url = f.url;
                pairing.error = '';
                render();
              },
            },
            h('div', {}, h('div', { class: 'what', text: f.name }), h('div', { class: 'addr', text: f.url })),
            h('span', { class: 'badge', text: f.via === 'mdns' ? 'on this network' : 'onemind.local' }),
          ),
        ),
      ),
    );
  }
  const urlIn = h('input', { type: 'text', placeholder: 'onemind.local:8080', value: pairing.url, spellcheck: 'false', autocapitalize: 'off' });
  urlIn.addEventListener('input', () => {
    pairing.url = urlIn.value;
    insecureRow.classList.toggle('hidden', !isInsecureAddress(pairing.url));
  });
  const tokIn = h('input', { type: 'password', placeholder: 'Paste the token', value: pairing.token, autocomplete: 'off' });
  tokIn.addEventListener('input', () => (pairing.token = tokIn.value));
  const cb = h('input', { type: 'checkbox', checked: pairing.insecure });
  cb.addEventListener('change', () => (pairing.insecure = cb.checked));
  const insecureRow = h('label', { class: `check ${isInsecureAddress(pairing.url) ? '' : 'hidden'}` }, cb, h('span', { text: 'This box has no HTTPS yet. Send the token over plain HTTP on my home network.' }));

  nodes.push(
    h(
      'section',
      { class: 'card', style: 'display:flex;flex-direction:column;gap:12px' },
      h('label', { class: 'field' }, 'Box address', urlIn),
      h('label', { class: 'field' }, 'Token', tokIn),
      insecureRow,
      pairing.error ? h('div', { class: 'error', text: errorText(pairing.error) }) : null,
      h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn', disabled: searching, onclick: search, text: searching ? 'Searching…' : 'Search again' }),
        h('button', { class: 'btn primary', disabled: pairing.busy, onclick: pair, text: pairing.busy ? 'Pairing…' : 'Pair' }),
      ),
      h('div', { class: 'note', text: 'The token is kept in your system keychain, not in a file. On the box, an owner token comes from the box setup.' }),
    ),
  );
  if (!first) nodes.push(h('button', { class: 'link small', text: '← Back', onclick: () => ((mode = 'home'), render()) }));
  return nodes;
}

function render() {
  view.replaceChildren(...[mode === 'add' ? addView() : homeView()].flat());
  const pending = boxes.reduce((n, b) => n + ((b.status && b.status.pending.length) || 0), 0);
  $('foot-note').textContent = boxes.length ? (pending ? `${pending} waiting for approval` : `${boxes.length === 1 ? '1 box' : `${boxes.length} boxes`} · checks every 20 s`) : 'Not paired yet';
}

async function run(cmd, args) {
  try {
    return await invoke(cmd, args);
  } catch (e) {
    toast(errorText(String(e)));
  }
}

let toastTimer;
function toast(text) {
  const t = $('toast');
  t.textContent = text;
  t.classList.remove('hidden');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add('hidden'), 6000);
}

async function load() {
  boxes = (await invoke('list_boxes')) || [];
  if (!boxes.length && !found.length && !searching) search();
  render();
}

async function search() {
  searching = true;
  render();
  try {
    found = await invoke('discover');
    if (found.length && !pairing.url) pairing.url = found[0].url;
  } catch {
    found = [];
  }
  searching = false;
  render();
}

async function pair() {
  pairing.busy = true;
  pairing.error = '';
  render();
  try {
    await invoke('pair', { url: pairing.url, token: pairing.token, allowInsecure: pairing.insecure });
    pairing = { url: '', token: '', insecure: false, error: '', busy: false };
    mode = 'home';
    await load();
  } catch (e) {
    pairing.busy = false;
    pairing.error = String(e);
    render();
  }
}

$('btn-add').addEventListener('click', () => {
  mode = 'add';
  render();
  search();
});
$('btn-refresh').addEventListener('click', async (ev) => {
  const b = ev.currentTarget;
  b.classList.add('spin');
  await run('refresh');
  await load();
  b.classList.remove('spin');
});
$('btn-close').addEventListener('click', () => invoke('hide'));
$('btn-quit').addEventListener('click', () => invoke('quit'));
document.addEventListener('keydown', (e) => e.key === 'Escape' && invoke('hide'));

tauri.event.listen('status', (ev) => {
  const st = ev.payload;
  const b = boxes.find((x) => x.id === st.box_id);
  if (b) {
    b.status = st;
    if (mode === 'home') render();
  } else load();
});
tauri.event.listen('shown', () => load());
setInterval(() => mode === 'home' && render(), 15000);
load();
