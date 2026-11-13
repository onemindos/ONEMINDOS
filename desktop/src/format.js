// SPDX-License-Identifier: Apache-2.0
// Pure helpers for the tray popover: wording for status, errors and ages.
// No DOM and no Tauri here, so `node --test` can check them.

const ERRORS = {
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
  conflict: 'The box refused: the request is no longer in a state that can be decided.',
};

/** `message` is the box's own words, used when the code is one this app does not know. */
export function errorText(code, message = '') {
  if (!code) return '';
  if (ERRORS[code]) return ERRORS[code];
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
