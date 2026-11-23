// SPDX-License-Identifier: Apache-2.0
// Pure helpers for the tray popover: wording for status, errors and ages.
// No DOM and no Tauri here, so `node --test` can check them.

const ERRORS = {
  no_update_pending: 'That update is no longer ready. It will be checked again shortly.',
  update_endpoint_refused: 'The update address was refused because it is not HTTPS.',
  unauthorized: 'The box did not accept this token. Create a new one on the box and try again.',
  unreachable: 'Cannot reach the box. Check that it is on and that this computer is on the same network.',
  needs_https:
    'This address uses plain HTTP, so your token would cross the network unencrypted. Use https://, or tick the box below if this box has no HTTPS yet.',
  invalid_address: 'That does not look like a box address. Example: onemind.local:8080',
  token_missing: 'Paste the token from your box.',
  not_a_onemind_box: 'Something answered at that address, but it is not a OneMind box.',
  keychain_unavailable: 'The system keychain is not available, so the token cannot be stored safely.',
  keychain_write_failed: 'The token could not be saved to the system keychain.',
  config_write_failed: 'The box list could not be saved.',
  bad_response: 'The box sent an answer this app does not understand. It may need an update.',
  open_failed: 'The system could not open that address.',
  unknown_box: 'This box is no longer in the list.',
  invalid_id: 'The box sent an id this app does not accept, so nothing was sent.',
  invalid_decision: 'Nothing was sent: unknown decision.',
  link_refused: 'That link points away from your box, so it was not opened.',
  http_404: 'The box no longer has this item.',
  permission_denied: 'This token may not do that. Only an owner can.',
  plan_changed: 'The plan changed after you looked at it. Nothing was sent; look at the new plan and try again.',
  invalid_box_name: 'The box name uses lower-case letters, digits and hyphens, 1 to 63 characters, and cannot start or end with a hyphen.',
  invalid_time_zone: 'Enter a time zone like Europe/Berlin, or UTC.',
  invalid_backup_choice: 'Pick USB disk, Another box, Cloud or Later.',
  destination_mismatch: 'That destination does not match the backup choice.',
  destination_not_allowed: 'A destination does not go with "Later".',
  unauthenticated: 'The box did not accept this token. Pair the box again.',
  rate_limited: 'The box asks to slow down. Try again in a minute.',
  unavailable: 'The box cannot do this right now. Try again shortly.',
  autostart_failed: 'The system would not change the start-at-login setting.',
  conflict: 'The box refused: the request is no longer in a state that can be decided.',
  join_missing: 'Paste the join link from your box, or type its code with the box address and fingerprint.',
  join_link_not_desktop: 'This join link is for another kind of device. On the box, make a link for a computer.',
  ca_pin_missing: 'Type the box fingerprint (64 letters and digits) shown next to the code. It proves the box is yours.',
  ca_mismatch: 'The box at that address does not have the certificate from the join link. Nothing was sent.',
  ca_invalid: 'The saved box certificate cannot be read. Remove the box and join it again.',
  password_missing: 'Enter your password.',
};

/** `message` is the box's own words, used when the code is one this app does not know. */
export function errorText(code, message = '') {
  if (!code) return '';
  if (ERRORS[code]) return ERRORS[code];
  if (code.startsWith('join_link_')) return 'That is not a OneMind join link. Copy the whole link from your box.';
  const m = /^http_(\d{3})$/.exec(code);
  if (m) return `The box answered with an error (${m[1]}).`;
  return message || 'Something went wrong.';
}

export function ago(fetchedAt, now = Date.now() / 1000) {
  if (!fetchedAt) return 'not checked yet';
  const s = Math.max(0, Math.round(now - fetchedAt));
  if (s < 10) return 'just now';
  if (s < 60) return `${s} s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.round(m / 60)} h ago`;
}

export function plural(n, one, many) {
  return `${n} ${n === 1 ? one : many}`;
}

/** Tone for a status tile: ok | warn | bad | neutral | agent. */
export function nodesTile(st) {
  if (!st.nodes_total) return { tone: 'neutral', value: '0', label: 'No nodes reporting' };
  const off = st.nodes_total - st.nodes_online;
  return {
    tone: off === 0 ? 'ok' : 'warn',
    value: `${st.nodes_online}/${st.nodes_total}`,
    label: off === 0 ? 'Nodes online' : `${plural(off, 'node', 'nodes')} offline`,
  };
}

export function approvalsTile(st) {
  const n = st.pending.length;
  return { tone: n ? 'agent' : 'ok', value: String(n), label: n ? 'Waiting for you' : 'Nothing to approve' };
}

export function updatesTile(st) {
  if (!st.updates) return { tone: 'neutral', value: '–', label: 'Updates not reported yet' };
  const u = st.updates;
  if (!u.available) return { tone: 'ok', value: '✓', label: 'Up to date' };
  return {
    tone: u.security ? 'bad' : 'warn',
    value: String(u.available),
    label: u.security ? 'Security update ready' : `${plural(u.available, 'update', 'updates')} ready`,
  };
}

const BACKUP = {
  ok: ['ok', 'Backed up'],
  verified: ['ok', 'Backup verified'],
  unverified: ['warn', 'Backup not verified'],
  stale: ['warn', 'Backup is old'],
  failing: ['bad', 'Backup failing'],
  none: ['bad', 'No backup yet'],
  not_configured: ['bad', 'Backups not set up'],
};

export function backupsTile(st, now = Date.now() / 1000) {
  if (!st.backups) return { tone: 'neutral', value: '–', label: 'Backups not reported yet' };
  const [tone, label] = BACKUP[st.backups.health] || ['neutral', 'Backup state unknown'];
  const last = st.backups.last_success_at ? Date.parse(st.backups.last_success_at) / 1000 : null;
  return { tone, value: tone === 'ok' ? '✓' : '!', label, detail: last ? `last ${ago(last, now)}` : undefined };
}

// ---- approvals (contract §12.3 risk classes, §12.4 approve; src-tauri/src/approvals.rs) ----

const RISK = {
  read: ['ok', 'Read only', 'It changes nothing that lasts.'],
  write: ['neutral', 'Reversible change', 'It changes something that can be undone.'],
  sensitive: ['warn', 'Widens access', 'It lets more run, or lets more people or apps reach something.'],
  destructive: ['bad', 'Can lose data', 'Data loss or downtime is possible.'],
  actuate: ['bad', 'Moves a device', 'It moves or switches a physical device.'],
};

export function riskInfo(risk) {
  const r = RISK[risk];
  if (!r) return { tone: 'neutral', label: 'Risk not reported', words: 'This box does not report a risk class yet.' };
  return { tone: r[0], label: r[1], words: r[2] };
}

export function actionTitle(d) {
  return d.target ? `${d.kind} · ${d.target}` : d.kind;
}

export function requesterText(d) {
  const who = d.requested_by || 'someone';
  return d.requester_kind ? `asked by ${who} (${d.requester_kind})` : `asked by ${who}`;
}

/** The requester's reason is their own words; an agent's words are marked as unchecked. */
export function reasonLabel(d) {
  const who = d.requested_by || 'the requester';
  if (d.requester_kind === 'person') return `Reason given by ${who}`;
  if (d.requester_kind) return `Reason given by ${who} (${d.requester_kind}), not checked by OneMind`;
  return `Reason given by ${who}, not checked by OneMind`;
}

export function expiresText(iso, now = Date.now() / 1000) {
  const t = iso ? Date.parse(iso) / 1000 : NaN;
  if (!Number.isFinite(t)) return '';
  const s = Math.round(t - now);
  if (s <= 0) return 'expired';
  if (s < 3600) return `expires in ${Math.max(1, Math.round(s / 60))} min`;
  if (s < 2 * 86400) return `expires in ${Math.round(s / 3600)} h`;
  return `expires in ${Math.round(s / 86400)} days`;
}

export function shortHash(h) {
  if (!h) return '';
  const [alg, hex] = h.includes(':') ? h.split(':', 2) : ['sha256', h];
  return `${alg}:${hex.slice(0, 12)}…`;
}

export function passkeyNote(d) {
  if (d.passkey === 'risk') return `${riskInfo(d.risk).words} It needs your passkey, so you approve it in your browser on the box's own page (Touch ID, Windows Hello or a security key).`;
  if (d.passkey === 'owner_passkey') return "You have a passkey on this box, so every approval needs it. You approve in your browser on the box's own page.";
  return 'No passkey is set up for this token yet, so this computer approves with its token. The box records the approval as "without passkey".';
}

export function confirmText(d) {
  return `Approve ${actionTitle(d)}? ${riskInfo(d.risk).words} Click "Confirm approve" to send it.`;
}

/** Result of `decide` (approvals.rs `Outcome`) in plain words, and the tone of its box. */
export function outcomeText(o) {
  switch (o && o.outcome) {
    case 'done':
      if (o.state === 'denied') return 'Denied. Nothing will change.';
      return o.approval === 'passkey' ? `Approved with your passkey (${o.state}).` : `Approved without passkey, with this computer's token (${o.state}).`;
    case 'browser':
      if (o.why === 'plan_unchecked') return 'This box wants the approval bound to a plan this app could not check. Nothing was approved here. Finish it in your browser.';
      return "This box asks for your passkey. Nothing was approved here. Finish it in your browser on the box's own page.";
    case 'plan_changed':
      return 'The request changed after you opened it, so nothing was approved. Check the new plan below and decide again.';
    case 'not_pending':
      return o.state === 'gone' ? 'This request is no longer on the box.' : `Nothing to do: the request is already ${String(o.state).replace(/_/g, ' ')}.`;
    case 'refused':
      return errorText(o.code, o.message);
    default:
      return '';
  }
}

export function outcomeTone(o) {
  const k = o && o.outcome;
  if (k === 'done') return 'ok';
  if (k === 'browser') return 'info';
  if (k === 'plan_changed' || k === 'not_pending') return 'warn';
  return 'bad';
}

// ---- inbox (contract §12.14; src-tauri/src/inbox.rs) ----

export function severityTone(sev) {
  return sev === 'critical' ? 'bad' : sev === 'warning' ? 'warn' : 'neutral';
}

export function itemAge(item, now = Date.now() / 1000) {
  const t = item.created_at ? Date.parse(item.created_at) / 1000 : NaN;
  return Number.isFinite(t) ? ago(t, now) : '';
}

/** Footer line: what needs the person, else how fresh the view is. */
export function footText(boxes) {
  if (!boxes.length) return 'Not paired yet';
  const pending = boxes.reduce((n, b) => n + ((b.status && b.status.pending.length) || 0), 0);
  const unread = boxes.reduce((n, b) => n + ((b.status && b.status.inbox && b.status.inbox.length) || 0), 0);
  const need = [pending ? `${pending} waiting for approval` : '', unread ? `${unread} unread` : ''].filter(Boolean);
  if (need.length) return need.join(' · ');
  const count = boxes.length === 1 ? '1 box' : `${boxes.length} boxes`;
  return boxes.some((b) => b.live) ? `${count} · live` : `${count} · checks every 20 s`;
}

/** Is this typed address plain HTTP to another machine? (mirrors address.rs) */
export function isInsecureAddress(input) {
  const raw = (input || '').trim().toLowerCase();
  if (!raw.startsWith('http://')) return false;
  const host = raw.slice(7).split(/[/:]/)[0];
  return !(host === 'localhost' || host.startsWith('127.') || raw.startsWith('http://[::1]'));
}

// ---- app updates (src-tauri/src/updates.rs; docs/UPDATER.md) ----

/** What the update strip shows, or null when there is nothing to show (off, or up to date). */
export function updateStrip(check) {
  const a = check && check.configured && check.available;
  if (!a || !a.version) return null;
  const dev = check.channel === 'dev' ? ' (dev channel)' : '';
  return {
    title: `Update available: OneMind ${a.version}${dev}`,
    detail: `You have ${a.current || 'an older version'}. Nothing installs until you click.`,
    notes: typeof a.notes === 'string' ? a.notes.trim().slice(0, 600) : '',
    action: 'Install and restart',
  };
}

// ---- "Needs you" and box health (D-016 home; src-tauri/src/api.rs parse_alerts, parse_os, parse_storage) ----

const SEV_RANK = { critical: 0, warning: 1, info: 2 };

/**
 * One list for everything a person has to look at: approvals first (they block someone), then open
 * alerts, worst first. An acknowledged alert is not counted (someone already saw it). `alertsServed`
 * says whether the box has an alerts route at all, so the popover can hide that part when it does not.
 */
export function needsYou(st) {
  const items = [];
  for (const p of st.pending || []) {
    items.push({ kind: 'approval', id: p.id, title: p.target ? `${p.kind} · ${p.target}` : p.kind, sub: `asked by ${p.requested_by || 'someone'}`, tone: 'agent' });
  }
  const open = (st.alerts || []).filter((a) => a.state === 'open').sort((a, b) => (SEV_RANK[a.severity] ?? 2) - (SEV_RANK[b.severity] ?? 2));
  for (const a of open) items.push({ kind: 'alert', id: a.id, title: a.title, sub: a.severity === 'critical' ? 'Critical alert' : 'Alert', tone: severityTone(a.severity), link: a.link || '/alerts' });
  return { count: items.length, items, alertsServed: Array.isArray(st.alerts) };
}

export function bytesText(n) {
  if (!Number.isFinite(n) || n < 0) return '';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = n;
  while (v >= 1000 && i < u.length - 1) {
    v /= 1000;
    i += 1;
  }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`;
}

const OS_BUSY = ['checking', 'downloading', 'installing', 'pending_reboot'];

/** The OS row: version and booted A/B slot, and what the update service is doing. `null`: not served. */
export function osRow(st) {
  const o = st.os;
  if (!o) return null;
  const where = [o.version ? `v${o.version}` : null, o.booted_slot ? `slot ${o.booted_slot}` : null].filter(Boolean).join(' · ') || 'running';
  if (o.state === 'rolled_back') return { label: 'System', tone: 'bad', value: where, note: 'The last update was rolled back by the health check.' };
  if (OS_BUSY.includes(o.state)) return { label: 'System', tone: 'warn', value: where, note: `Update ${o.state.replace(/_/g, ' ')}.` };
  if (o.available_version) return { label: 'System', tone: 'warn', value: where, note: `Update ${o.available_version} is ready.` };
  return { label: 'System', tone: 'ok', value: where, note: 'Up to date.' };
}

export function storageRow(st) {
  const s = st.storage;
  if (!s || !s.available) return null; // the box has no managed storage: say nothing
  const used = s.used_bytes != null ? (s.total_bytes ? `${bytesText(s.used_bytes)} of ${bytesText(s.total_bytes)}` : `${bytesText(s.used_bytes)} used`) : 'in use';
  if (s.missing > 0) return { label: 'Storage', tone: 'bad', value: used, note: `${plural(s.missing, 'disk is', 'disks are')} missing.` };
  if (s.state && s.state !== 'healthy' && s.state !== 'ok') return { label: 'Storage', tone: 'warn', value: used, note: `State: ${s.state}.` };
  if (s.needs_scrub) return { label: 'Storage', tone: 'warn', value: used, note: 'A data check is due.' };
  return { label: 'Storage', tone: 'ok', value: used, note: s.members > 1 ? `${s.members} disks, healthy.` : 'Healthy.' };
}

export function backupRow(st, now = Date.now() / 1000) {
  if (!st.backups) return null;
  const t = backupsTile(st, now);
  return { label: 'Backups', tone: t.tone, value: t.label, note: t.detail || '' };
}

/** Rows for the "Box health" list; a row whose route the box does not serve is simply absent. */
export function healthRows(st, now = Date.now() / 1000) {
  return [osRow(st), backupRow(st, now), storageRow(st)].filter(Boolean);
}

/** The Files button for this computer (files-webdav, #722): Finder mounts the box over WebDAV, a Linux
 * file manager opens davs://, Windows opens the SMB share. `platform` is navigator.platform. */
export function filesLabel(platform = '') {
  const p = String(platform).toLowerCase();
  if (p.startsWith('mac')) return { text: 'Open in Finder', title: 'Mounts your files from the box in Finder. Sign in with an app password (Settings, Account and security, on the box).' };
  if (p.startsWith('win')) return { text: 'Open in Explorer', title: "Opens the box's file share (SMB) in File Explorer." };
  return { text: 'Open in Files', title: 'Opens your files from the box in your file manager (davs://). Sign in with an app password from the box.' };
}
