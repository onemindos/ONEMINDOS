// SPDX-License-Identifier: Apache-2.0
// Tray popover. Every call goes to a Rust command; this page has no network, file or shell
// permission of its own (see src-tauri/capabilities/default.json). Text from the box is
// only ever set with textContent, never parsed as HTML.

import {
  actionTitle,
  ago,
  approvalsTile,
  backupsTile,
  confirmText,
  errorText,
  expiresText,
  footText,
  isInsecureAddress,
  itemAge,
  nodesTile,
  outcomeText,
  outcomeTone,
  passkeyNote,
  reasonLabel,
  requesterText,
  riskInfo,
  severityTone,
  shortHash,
  updatesTile,
} from './format.js';

const tauri = window.__TAURI__;
const invoke = (cmd, args) => tauri.core.invoke(cmd, args);
const $ = (id) => document.getElementById(id);
const view = $('view');

let mode = 'home'; // home | add | approval | inbox
let boxes = [];
let found = [];
let searching = false;
let pairing = { url: '', token: '', insecure: false, error: '', busy: false };
// Approval card: { boxId, actionId, detail, error, busy, result, confirm: '' | 'approve' | 'deny', reason }
let card = null;
// Inbox: { boxId, items: null | [...], error, loading }
let inbox = null;

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

function back() {
  mode = 'home';
  card = null;
  inbox = null;
  load();
}

// ---- home: one card per box ----

function inboxSection(b, st) {
  if (!st.inbox) return null; // this box keeps no inbox for this token: say nothing rather than "all clear"
  const unread = st.inbox;
  return h(
    'div',
    {},
    h('div', { class: 'section-title', text: unread.length ? `Notifications · ${unread.length} unread` : 'Notifications' }),
    unread.length
      ? h(
          'div',
          { class: 'pending' },
          unread.slice(0, 3).map((it) =>
            h(
              'button',
              { class: 'inbox-item compact unread', onclick: () => openItem(b.id, it) },
              h('span', { class: `dot ${severityTone(it.severity)}` }),
              h('span', { class: 'what', text: it.title || 'New notification' }),
            ),
          ),
        )
      : null,
    h('button', { class: 'link small', text: unread.length ? 'See all notifications' : 'No unread notifications · see all', onclick: () => openInbox(b.id) }),
  );
}

function boxCard(b) {
  const st = b.status;
  const online = st && st.reachable;
  const sub = h(
    'div',
    { class: 'box-sub' },
    h('span', { class: `dot ${st ? (online ? 'ok' : 'bad') : ''}` }),
    h('span', { text: !st ? 'Checking…' : online ? `Online${st.version ? ` · v${st.version}` : ''}` : 'Not reachable' }),
    b.live && online ? h('span', { class: 'badge', title: 'Changes on the box arrive within seconds.', text: 'Live' }) : null,
    b.insecure ? h('span', { class: 'badge warn', title: 'This box is paired over plain HTTP.', text: 'Not encrypted' }) : null,
  );
  const el = h('section', { class: 'card' }, h('div', { class: 'box-head' }, h('div', {}, h('div', { class: 'box-name', text: (st && st.name) || b.name }), sub)));

  if (st && !online) el.append(h('div', { class: 'error', style: 'margin-top:12px', text: errorText(st.error) }));
  if (st && online) {
    el.append(h('div', { class: 'tiles' }, tile(nodesTile(st)), tile(approvalsTile(st)), tile(updatesTile(st)), tile(backupsTile(st))));
    if (st.pending.length) {
      el.append(
        h('div', { class: 'section-title', text: 'Waiting for your approval' }),
        h(
          'div',
          { class: 'pending' },
          st.pending.slice(0, 4).map((p) =>
            h(
              'div',
              { class: 'pending-item' },
              h('div', {}, h('div', { class: 'what', text: p.target ? `${p.kind} · ${p.target}` : p.kind }), h('div', { class: 'who', text: `asked by ${p.requested_by || 'someone'}` })),
              h('button', { class: 'btn small', text: 'Review', onclick: () => openApproval(b.id, p.id) }),
            ),
          ),
        ),
        h('div', { class: 'note', style: 'margin-top:6px', text: 'Review shows the exact plan first. A notification never approves anything.' }),
      );
    }
    el.append(inboxSection(b, st) || '');
  }
  el.append(
    h(
      'div',
      { class: 'actions' },
      h('button', { class: 'btn primary', onclick: () => run('open_dashboard', { id: b.id }) }, icon('globe'), 'Open dashboard'),
      h('button', { class: 'btn', title: "Opens the box's file share in your file manager", onclick: () => run('open_files', { id: b.id }) }, icon('folder'), 'Files'),
    ),
  );
  el.append(
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
  return el;
}

function homeView() {
  if (!boxes.length) return addView(true);
  return boxes.map(boxCard);
}

// ---- approval card ----

async function openApproval(boxId, actionId) {
  mode = 'approval';
  const c = { boxId, actionId, detail: null, error: '', busy: true, result: null, confirm: '', reason: '' };
  card = c;
  render();
  try {
    c.detail = await invoke('approval', { id: boxId, actionId });
  } catch (e) {
    c.error = String(e);
  }
  c.busy = false;
  if (card === c) render();
}

async function decideNow(decision) {
  const c = card;
  c.busy = true;
  render();
  try {
    c.result = await invoke('decide', {
      id: c.boxId,
      actionId: c.actionId,
      decision,
      planSha256: c.detail.plan_sha256 ?? null,
      reason: decision === 'deny' ? c.reason : null,
    });
    // Show what the box holds now: a changed plan, or the decided state.
    c.detail = await invoke('approval', { id: c.boxId, actionId: c.actionId }).catch(() => c.detail);
  } catch (e) {
    c.result = { outcome: 'refused', code: String(e), message: '' };
  }
  c.busy = false;
  c.confirm = '';
  if (card === c) render();
}

function planNodes(d) {
  if (!d.plan) {
    return [h('div', { class: 'note', text: 'This box sent no plan for this request. You decide on the request exactly as filed:' }), h('pre', { class: 'params', text: JSON.stringify(d.params, null, 2) })];
  }
  const p = d.plan;
  const rows = [];
  if (p.images.length) rows.push(['Images', p.images.join(', ')]);
  if (p.volumes) rows.push(['Storage', `${p.volumes} volume${p.volumes === 1 ? '' : 's'}`]);
  if (p.nodes.length) rows.push(['Machines', p.nodes.join(', ')]);
  if (p.objects) rows.push(['Objects', String(p.objects)]);
  if (d.plan_sha256) rows.push(['Plan', shortHash(d.plan_sha256)]);
  return [
    h('div', { class: 'plan-summary', text: p.summary || 'The box sent a plan without a summary.' }),
    p.warnings.length ? h('ul', { class: 'warnings' }, p.warnings.map((w) => h('li', { text: w }))) : null,
    rows.length ? h('dl', { class: 'facts' }, rows.map(([k, v]) => [h('dt', { text: k }), h('dd', { text: v })])) : null,
  ];
}

function decisionRow(c, d) {
  const disabled = c.busy;
  if (c.confirm === 'deny') {
    const r = h('input', { type: 'text', placeholder: 'Reason (optional, shown to the requester)', value: c.reason, maxlength: '500' });
    r.addEventListener('input', () => (c.reason = r.value));
    return h(
      'div',
      { class: 'stack' },
      r,
      h(
        'div',
        { class: 'row' },
        h('button', { class: 'btn', text: 'Cancel', onclick: () => ((c.confirm = ''), render()) }),
        h('button', { class: 'btn danger', disabled, text: c.busy ? 'Denying…' : 'Confirm deny', onclick: () => decideNow('deny') }),
      ),
    );
  }
  const approve = d.passkey
    ? h('button', { class: 'btn primary', title: "Your passkey is checked on the box's own page", text: 'Approve in browser', onclick: () => run('open_approvals', { id: c.boxId }) })
    : h('button', {
        class: 'btn primary',
        disabled,
        text: c.busy ? 'Approving…' : c.confirm === 'approve' ? 'Confirm approve' : 'Approve…',
        onclick: () => (c.confirm === 'approve' ? decideNow('approve') : ((c.confirm = 'approve'), render())),
      });
  return h(
    'div',
    { class: 'stack' },
    c.confirm === 'approve' ? h('div', { class: 'check', text: confirmText(d) }) : null,
    h('div', { class: 'row' }, h('button', { class: 'btn', disabled, text: 'Deny…', onclick: () => ((c.confirm = 'deny'), render()) }), approve),
  );
}

function approvalView() {
  const c = card;
  const nodes = [h('button', { class: 'link small', text: '← Back', onclick: back })];
  if (c.busy && !c.detail) nodes.push(h('div', { class: 'note', text: 'Reading the request from the box…' }));
  if (c.error) nodes.push(h('div', { class: 'error', text: errorText(c.error) }));
  const d = c.detail;
  if (!d) return nodes;
  const risk = riskInfo(d.risk);
  const waiting = d.state === 'awaiting_approval';
  nodes.push(
    h(
      'section',
      { class: 'card approval' },
      h('div', { class: 'row-between' }, h('span', { class: `badge ${risk.tone}`, title: risk.words, text: risk.label }), h('span', { class: 'note', text: expiresText(d.expires_at) })),
      h('h2', { class: 'title', text: actionTitle(d) }),
      h('div', { class: 'who', text: requesterText(d) }),
      d.reason ? h('div', { class: 'quote' }, h('div', { class: 'quote-label', text: reasonLabel(d) }), h('div', { text: d.reason })) : null,
      h('div', { class: 'section-title', text: 'What will happen' }),
      planNodes(d),
      waiting ? h('div', { class: 'note', text: passkeyNote(d) }) : null,
      c.result ? h('div', { class: `result ${outcomeTone(c.result)}`, role: 'status', text: outcomeText(c.result) }) : null,
      c.result && c.result.outcome === 'browser' ? h('button', { class: 'btn', text: 'Open approvals in browser', onclick: () => run('open_approvals', { id: c.boxId }) }) : null,
      waiting ? decisionRow(c, d) : h('div', { class: 'note', text: `This request is ${d.state.replace(/_/g, ' ')}. Nothing to decide.` }),
      h(
        'details',
        { class: 'api' },
        h('summary', { text: 'Exact request and API equivalent' }),
        h('pre', { class: 'params', text: `POST /v1/actions/${d.id}/approve\nPOST /v1/actions/${d.id}/deny\n\n${JSON.stringify(d.params, null, 2)}` }),
      ),
    ),
  );
  return nodes;
}

// ---- inbox ----

async function openInbox(boxId) {
  mode = 'inbox';
  const v = { boxId, items: null, error: '', loading: true };
  inbox = v;
  render();
  try {
    v.items = await invoke('inbox', { id: boxId });
  } catch (e) {
    v.error = String(e);
  }
  v.loading = false;
  if (inbox === v) render();
}

async function openItem(boxId, it) {
  if (!it.read_at) {
    await run('inbox_read', { id: boxId, itemId: it.id });
    it.read_at = 'now';
  }
  if (it.action_id) return openApproval(boxId, it.action_id);
  if (it.link) await run('open_link', { id: boxId, link: it.link });
  if (mode === 'inbox') render();
}

function inboxView() {
  const v = inbox;
  const b = boxes.find((x) => x.id === v.boxId);
  const hasUnread = (v.items || []).some((it) => !it.read_at);
  const nodes = [
    h('button', { class: 'link small', text: '← Back', onclick: back }),
    h(
      'div',
      { class: 'row-between' },
      h('h2', { class: 'title', text: `Notifications${b ? ` · ${(b.status && b.status.name) || b.name}` : ''}` }),
      hasUnread
        ? h('button', {
            class: 'link small',
            text: 'Mark all read',
            onclick: async () => {
              await run('inbox_read', { id: v.boxId, itemId: null });
              openInbox(v.boxId);
            },
          })
        : null,
    ),
  ];
  if (v.loading) nodes.push(h('div', { class: 'note', text: 'Reading the inbox from the box…' }));
  if (v.error) nodes.push(h('div', { class: 'error', text: errorText(v.error) }));
  if (!v.loading && !v.error && v.items === null) nodes.push(h('div', { class: 'note', text: "This box does not keep a notifications inbox yet, or this computer's token is not a person's." }));
  if (v.items && !v.items.length) nodes.push(h('div', { class: 'note', text: 'No notifications.' }));
  if (v.items && v.items.length) {
    nodes.push(
      h(
        'div',
        { class: 'pending' },
        v.items.map((it) =>
          h(
            'button',
            { class: `inbox-item ${it.read_at ? '' : 'unread'}`, title: it.action_id ? 'Opens the approval card' : it.link ? "Opens the box's page in your browser" : '', onclick: () => openItem(v.boxId, it) },
            h('span', { class: `dot ${severityTone(it.severity)}` }),
            h('span', { class: 'body' }, h('span', { class: 'what', text: it.title || 'Notification' }), it.body ? h('span', { class: 'text', text: it.body }) : null, h('span', { class: 'meta', text: [itemAge(it), it.topic].filter(Boolean).join(' · ') })),
          ),
        ),
      ),
    );
  }
  return nodes;
}

// ---- add a box ----

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
  const urlIn = h('input', { type: 'text', placeholder: 'onemind.local:8443', value: pairing.url, spellcheck: 'false', autocapitalize: 'off' });
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
  if (!first) nodes.push(h('button', { class: 'link small', text: '← Back', onclick: back }));
  return nodes;
}

const VIEWS = { home: homeView, add: () => addView(), approval: approvalView, inbox: inboxView };

function render() {
  view.replaceChildren(...[VIEWS[mode]()].flat());
  $('foot-note').textContent = footText(boxes);
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
  if (mode === 'home' || mode === 'add') render();
  else $('foot-note').textContent = footText(boxes);
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
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (mode === 'approval' || mode === 'inbox') back();
  else invoke('hide');
});

tauri.event.listen('status', (ev) => {
  const st = ev.payload;
  const b = boxes.find((x) => x.id === st.box_id);
  if (b) {
    b.status = st;
    if (mode === 'home') render();
    else $('foot-note').textContent = footText(boxes);
  } else load();
});
tauri.event.listen('live', (ev) => {
  const b = boxes.find((x) => x.id === ev.payload.box_id);
  if (b) b.live = ev.payload.live;
  if (mode === 'home') render();
});
tauri.event.listen('shown', () => load());
setInterval(() => mode === 'home' && render(), 15000);
load();
