// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { backupHealth, destinationsFor, filedText, isOwner, lifecycleLabel, planCard, settingsProblem, validBoxName } from '../src/manage.js';
import { errorText } from '../src/format.js';

const dests = [
  { id: 'dst_1', kind: 'usb', label: 'USB' },
  { id: 'dst_2', kind: 'box', label: 'Peer' },
  { id: 'dst_3', kind: 's3', label: 'Bucket' },
];
const good = { box_name: 'home', time_zone: 'Europe/Berlin', backup_choice: 'usb', backup_destination_id: 'dst_1' };

test('lifecycle labels cover the five requests and nothing destructive', () => {
  assert.equal(lifecycleLabel('app.restart'), 'Restart');
  assert.equal(lifecycleLabel('app.remove'), 'Remove');
  assert.equal(lifecycleLabel('app.delete_data'), 'app.delete_data', 'delete-data has no button, so no label');
});

test('owner is known only when the box said so', () => {
  assert.equal(isOwner({ me: { kind: 'person', role: 'owner' } }), true);
  assert.equal(isOwner({ me: { kind: 'person', role: 'adult' } }), false);
  assert.equal(isOwner({ me: { kind: 'agent', role: 'owner' } }), false);
  assert.equal(isOwner({ me: null }), null);
  assert.equal(isOwner(undefined), null);
});

test('backup health wording', () => {
  assert.deepEqual(backupHealth('ok'), { tone: 'ok', label: 'Protected' });
  assert.deepEqual(backupHealth('failing'), { tone: 'bad', label: 'Failing' });
  assert.equal(backupHealth('what').label, 'Unknown');
});

test('a refused plan cannot be sent; a normal one can, and shows versions and storage', () => {
  const refused = planCard({ verdict: 'refused', reason: 'already stopped' });
  assert.equal(refused.canSend, false);
  assert.match(refused.title, /will not file this now: already stopped/);
  const ok = planCard({ verdict: 'needs_approval', summary: 'Update ollama', from_version: '0.5', to_version: '0.6', volumes: 1, risk: 'write', plan_sha256: 'sha256:a' });
  assert.equal(ok.canSend, true);
  assert.deepEqual(ok.facts, [['Version', '0.5 → 0.6'], ['Storage', '1 volume'], ['Risk', 'write']]);
  assert.equal(planCard({ verdict: 'needs_approval', plan_sha256: null }).canSend, false, 'no hash, no request');
});

test('a filed request says nothing has changed yet', () => {
  assert.match(filedText({ state: 'awaiting_approval' }), /awaiting approval\)\. Nothing has changed yet/);
});

test('box name and settings checks match the Rust side', () => {
  for (const n of ['', 'Home', '-a', 'a-', 'a b', 'x'.repeat(64)]) assert.equal(validBoxName(n), false, n);
  assert.equal(validBoxName('a'), true);
  assert.equal(settingsProblem(good, dests), null);
  assert.equal(settingsProblem({ ...good, box_name: 'Home' }, dests), 'invalid_box_name');
  assert.equal(settingsProblem({ ...good, time_zone: '/etc/localtime' }, dests), 'invalid_time_zone');
  assert.equal(settingsProblem({ ...good, backup_choice: 's3' }, dests), 'destination_mismatch');
  assert.equal(settingsProblem({ ...good, backup_choice: 'later' }, dests), 'destination_not_allowed');
  assert.equal(settingsProblem({ ...good, backup_choice: 'peer', backup_destination_id: 'dst_2' }, dests), null);
  assert.deepEqual(destinationsFor('peer', dests).map((d) => d.id), ['dst_2']);
  assert.deepEqual(destinationsFor('later', dests), []);
});

test('every code the Manage view can get has plain words', () => {
  for (const c of ['permission_denied', 'plan_changed', 'invalid_box_name', 'invalid_time_zone', 'destination_mismatch', 'destination_not_allowed', 'rate_limited', 'conflict']) {
    assert.notEqual(errorText(c), 'Something went wrong.', c);
  }
  assert.match(errorText('plan_changed'), /Nothing was sent/);
});
