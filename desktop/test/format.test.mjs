// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  ago,
  approvalsTile,
  backupsTile,
  confirmText,
  errorText,
  filesLabel,
  expiresText,
  footText,
  isInsecureAddress,
  nodesTile,
  outcomeText,
  outcomeTone,
  passkeyNote,
  reasonLabel,
  requesterText,
  riskInfo,
  severityTone,
  shortHash,
  updateStrip,
  updatesTile,
} from '../src/format.js';

const base = { nodes_total: 3, nodes_online: 3, pending: [], updates: null, backups: null };

test('ages', () => {
  assert.equal(ago(100, 105), 'just now');
  assert.equal(ago(100, 145), '45 s ago');
  assert.equal(ago(100, 100 + 180), '3 min ago');
  assert.equal(ago(0), 'not checked yet');
});

test('nodes tile', () => {
  assert.equal(nodesTile(base).tone, 'ok');
  assert.equal(nodesTile({ ...base, nodes_online: 2 }).label, '1 node offline');
});

test('approvals use the agent tone when something waits', () => {
  assert.equal(approvalsTile({ ...base, pending: [{ id: 'a' }] }).tone, 'agent');
});

test('planned routes missing are neutral, never "all good"', () => {
  assert.equal(updatesTile(base).tone, 'neutral');
  assert.equal(backupsTile(base).tone, 'neutral');
});

test('security update is bad tone', () => {
  assert.equal(updatesTile({ ...base, updates: { available: 1, security: true } }).tone, 'bad');
});

test('backup states', () => {
  assert.equal(backupsTile({ ...base, backups: { health: 'not_configured' } }).tone, 'bad');
  assert.equal(backupsTile({ ...base, backups: { health: 'verified' } }).tone, 'ok');
});

test('errors', () => {
  assert.match(errorText('unauthorized'), /token/);
  assert.match(errorText('http_500'), /500/);
});

test('insecure address check mirrors address.rs', () => {
  assert.equal(isInsecureAddress('http://onemind.local:8080'), true);
  assert.equal(isInsecureAddress('http://127.0.0.1:8080'), false);
  assert.equal(isInsecureAddress('http://localhost'), false);
  assert.equal(isInsecureAddress('https://onemind.local'), false);
  assert.equal(isInsecureAddress('onemind.local:8080'), false);
});

test('unknown error codes fall back to the box message, then a generic line', () => {
  assert.equal(errorText('policy_refused', 'the sandbox refused the plan'), 'the sandbox refused the plan');
  assert.equal(errorText('policy_refused'), 'Something went wrong.');
  assert.match(errorText('link_refused'), /away from your box/);
});

test('risk classes: destructive is bad, unknown is neutral and says so', () => {
  assert.equal(riskInfo('destructive').tone, 'bad');
  assert.equal(riskInfo('sensitive').tone, 'warn');
  assert.equal(riskInfo('read').tone, 'ok');
  assert.deepEqual(riskInfo(undefined), { tone: 'neutral', label: 'Risk not reported', words: 'This box does not report a risk class yet.' });
});

test('an agent reason is marked as unchecked; a person reason is not', () => {
  assert.match(reasonLabel({ requested_by: 'agent:hermes', requester_kind: 'agent' }), /not checked by OneMind/);
  assert.doesNotMatch(reasonLabel({ requested_by: 'person:ana', requester_kind: 'person' }), /not checked/);
  assert.match(reasonLabel({ requested_by: 'hermes' }), /not checked by OneMind/);
  assert.equal(requesterText({ requested_by: 'agent:hermes', requester_kind: 'agent' }), 'asked by agent:hermes (agent)');
});

test('passkey note follows the reason the box needs one', () => {
  assert.match(passkeyNote({ passkey: 'risk', risk: 'destructive' }), /browser/);
  assert.match(passkeyNote({ passkey: 'owner_passkey' }), /every approval needs it/);
  assert.match(passkeyNote({ passkey: null }), /without passkey/);
  assert.match(confirmText({ kind: 'app.install', target: 'ntfy', risk: 'sensitive' }), /Approve app.install · ntfy\?/);
});

test('decision outcomes: nothing is ever called approved unless the box said so', () => {
  assert.equal(outcomeTone({ outcome: 'done', state: 'accepted' }), 'ok');
  assert.match(outcomeText({ outcome: 'done', state: 'accepted', approval: 'token' }), /without passkey/);
  assert.match(outcomeText({ outcome: 'done', state: 'accepted', approval: 'passkey' }), /with your passkey/);
  assert.match(outcomeText({ outcome: 'done', state: 'denied' }), /^Denied/);
  for (const o of [{ outcome: 'browser', why: 'step_up' }, { outcome: 'plan_changed' }, { outcome: 'browser', why: 'plan_unchecked' }]) {
    assert.match(outcomeText(o), /[Nn]othing was approved/);
    assert.notEqual(outcomeTone(o), 'ok');
  }
  assert.match(outcomeText({ outcome: 'not_pending', state: 'outcome_unknown' }), /already outcome unknown/);
  assert.equal(outcomeText({ outcome: 'refused', code: 'permission_denied', message: '' }), errorText('permission_denied'));
});

test('expiry, hashes, severity', () => {
  const now = Date.parse('2026-11-12T10:00:00Z') / 1000;
  assert.equal(expiresText('2026-11-12T10:30:00Z', now), 'expires in 30 min');
  assert.equal(expiresText('2026-11-13T09:00:00Z', now), 'expires in 23 h');
  assert.equal(expiresText('2026-11-12T09:00:00Z', now), 'expired');
  assert.equal(expiresText(null, now), '');
  assert.equal(shortHash('sha256:0123456789abcdef0123'), 'sha256:0123456789ab…');
  assert.equal(severityTone('critical'), 'bad');
  assert.equal(severityTone('warning'), 'warn');
  assert.equal(severityTone('info'), 'neutral');
});

test('footer says what needs you first, and only says live when a stream is open', () => {
  const st = { ...base, pending: [{ id: 'a' }], inbox: [{ id: 'n' }, { id: 'm' }] };
  assert.equal(footText([{ status: st }]), '1 waiting for approval · 2 unread');
  assert.equal(footText([{ status: { ...base, inbox: null }, live: true }]), '1 box · live');
  assert.equal(footText([{ status: { ...base, inbox: [] } }, { status: null }]), '2 boxes · checks every 20 s');
  assert.equal(footText([]), 'Not paired yet');
});

test('updateStrip: nothing to show when updates are off, current, or malformed', () => {
  assert.equal(updateStrip(null), null);
  assert.equal(updateStrip({ configured: false, channel: 'stable', current: '0.1.0', available: { version: '0.2.0' } }), null);
  assert.equal(updateStrip({ configured: true, channel: 'stable', current: '0.1.0', available: null }), null);
  assert.equal(updateStrip({ configured: true, channel: 'stable', current: '0.1.0', available: {} }), null);
});

test('updateStrip: an offer says nothing installs until the click', () => {
  const u = updateStrip({ configured: true, channel: 'stable', current: '0.1.0', available: { version: '0.2.0', current: '0.1.0', notes: '  Fixes a crash.  ' } });
  assert.equal(u.title, 'Update available: OneMind 0.2.0');
  assert.match(u.detail, /Nothing installs until you click/);
  assert.equal(u.notes, 'Fixes a crash.');
  assert.equal(u.action, 'Install and restart');
});

test('updateStrip: dev channel is named, long notes are cut, non-text notes dropped', () => {
  const u = updateStrip({ configured: true, channel: 'dev', current: '0.2.0-dev.1', available: { version: '0.2.0-dev.2', current: '0.2.0-dev.1', notes: 'x'.repeat(2000) } });
  assert.match(u.title, /\(dev channel\)/);
  assert.equal(u.notes.length, 600);
  assert.equal(updateStrip({ configured: true, channel: 'stable', available: { version: '1.0.0', notes: { a: 1 } } }).notes, '');
});

import { backupRow, bytesText, healthRows, needsYou, osRow, storageRow } from '../src/format.js';

test('needs you lists approvals first, then open alerts worst first, and skips acknowledged ones', () => {
  const st = {
    pending: [{ id: 'a1', kind: 'app.install', target: 'ntfy', requested_by: 'hermes' }],
    alerts: [
      { id: 'w', severity: 'warning', title: 'Slow disk', state: 'open' },
      { id: 'c', severity: 'critical', title: 'Disk failing', state: 'open', link: '/storage' },
      { id: 'k', severity: 'critical', title: 'Seen already', state: 'acknowledged' },
    ],
  };
  const n = needsYou(st);
  assert.equal(n.count, 3);
  assert.deepEqual(n.items.map((i) => i.id), ['a1', 'c', 'w']);
  assert.equal(n.items[1].link, '/storage');
  assert.equal(n.items[2].link, '/alerts');
  assert.equal(n.alertsServed, true);
});

test('needs you says the alerts route is absent when the box did not serve it', () => {
  const n = needsYou({ pending: [], alerts: null });
  assert.deepEqual([n.count, n.alertsServed], [0, false]);
});

test('os row shows the booted slot and never claims up to date while an update is busy or offered', () => {
  assert.equal(osRow({ os: null }), null);
  const base = { version: '0.4.1', booted_slot: 'A', state: 'idle', available_version: null };
  assert.deepEqual([osRow({ os: base }).tone, osRow({ os: base }).value], ['ok', 'v0.4.1 · slot A']);
  assert.equal(osRow({ os: { ...base, available_version: '0.4.2' } }).tone, 'warn');
  assert.equal(osRow({ os: { ...base, state: 'installing' } }).tone, 'warn');
  assert.equal(osRow({ os: { ...base, state: 'rolled_back' } }).tone, 'bad');
});

test('storage row hides without managed storage and is never green with a missing disk', () => {
  assert.equal(storageRow({ storage: null }), null);
  assert.equal(storageRow({ storage: { available: false } }), null);
  const ok = { available: true, state: 'healthy', used_bytes: 400e9, total_bytes: 2e12, members: 2, missing: 0, needs_scrub: false };
  assert.equal(storageRow({ storage: ok }).value, '400 GB of 2.0 TB');
  assert.equal(storageRow({ storage: { ...ok, missing: 1 } }).tone, 'bad');
  assert.equal(storageRow({ storage: { ...ok, state: 'degraded' } }).tone, 'warn');
});

test('health rows hide what the box does not report and bytes read plainly', () => {
  assert.deepEqual(healthRows({ os: null, backups: null, storage: null }), []);
  assert.equal(backupRow({ backups: { health: 'failing', last_success_at: null } }).tone, 'bad');
  assert.equal(bytesText(999), '999 B');
  assert.equal(bytesText(1500), '1.5 KB');
});

test('the Files button names the file manager of this computer (#722)', () => {
  assert.equal(filesLabel('MacIntel').text, 'Open in Finder');
  assert.match(filesLabel('MacIntel').title, /app password/);
  assert.equal(filesLabel('Win32').text, 'Open in Explorer');
  assert.match(filesLabel('Win32').title, /SMB/);
  assert.equal(filesLabel('Linux x86_64').text, 'Open in Files');
  assert.equal(filesLabel(undefined).text, 'Open in Files');
});
