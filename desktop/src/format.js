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
};

export function errorText(code) {
  if (!code) return '';
  if (ERRORS[code]) return ERRORS[code];
  const m = /^http_(\d{3})$/.exec(code);
  if (m) return `The box answered with an error (${m[1]}).`;
  return 'Something went wrong.';
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

/** Is this typed address plain HTTP to another machine? (mirrors address.rs) */
export function isInsecureAddress(input) {
  const raw = (input || '').trim().toLowerCase();
  if (!raw.startsWith('http://')) return false;
  const host = raw.slice(7).split(/[/:]/)[0];
  return !(host === 'localhost' || host.startsWith('127.') || raw.startsWith('http://[::1]'));
}
