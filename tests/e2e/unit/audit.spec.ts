// SPDX-License-Identifier: Apache-2.0
/** Unit tests for the e2e audit verifier (no hub, no browser). */
import { readFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { canonicalJson, chainHash, GENESIS, verifyChain } from '../lib/audit';

function chain(n: number): string[] {
  const lines: string[] = [];
  let prev = GENESIS;
  for (let i = 1; i <= n; i++) {
    const body = {
      seq: i,
      ts: `2026-11-12T00:00:0${i}Z`,
      event: 'action.requested',
      principal: { id: 'owner', kind: 'person', role: 'owner' },
      action_id: `a-${i}`,
      data: { params: { app_id: 'ntfy' }, note: 'café ✓' },
    };
    const hash = chainHash(prev, body);
    lines.push(JSON.stringify({ ...body, prev_hash: prev, hash }));
    prev = hash;
  }
  return lines;
}

test('canonical JSON matches Python json.dumps(sort_keys=True, separators=(",",":"), ensure_ascii=False)', () => {
  // Expected values produced with CPython 3.12 from the same objects.
  expect(canonicalJson({ b: 1, a: [true, null, 'x'], 'é': 'ü', A: { z: 0, y: '"\n' } })).toBe(
    '{"A":{"y":"\\"\\n","z":0},"a":[true,null,"x"],"b":1,"é":"ü"}',
  );
  expect(chainHash(GENESIS, { seq: 1, event: 'x', data: {} })).toBe(
    'd8bcd244287734685659e9c4ac0785aa9c291de305b3b81ffadbcbb9d41bbf44',
  );
});

test('a log written by the gateway AuditLog verifies (core/onemind_core/audit.py)', () => {
  // unit/fixtures/audit-sample.jsonl was written by core's AuditLog (see tests/e2e/README.md).
  const text = readFileSync(new URL('./fixtures/audit-sample.jsonl', import.meta.url), 'utf8');
  const r = verifyChain(text);
  expect(r.problem).toBeUndefined();
  expect(r.records.map((x) => x.event)).toEqual([
    'action.requested', 'action.awaiting_approval', 'authz.denied', 'action.approved', 'action.succeeded',
  ]);
});

test('an intact chain verifies', () => {
  const r = verifyChain(chain(5).join('\n') + '\n');
  expect(r.ok).toBe(true);
  expect(r.records).toHaveLength(5);
});

test('a changed, removed or reordered line is caught at that line', () => {
  const lines = chain(5);
  const changed = [...lines];
  changed[2] = changed[2].replace('ntfy', 'evil');
  expect(verifyChain(changed.join('\n'))).toMatchObject({ ok: false, firstBadLine: 3, problem: 'hash mismatch' });

  const removed = lines.filter((_, i) => i !== 1);
  expect(verifyChain(removed.join('\n'))).toMatchObject({ ok: false, firstBadLine: 2, problem: 'prev_hash does not link' });

  const swapped = [lines[0], lines[2], lines[1], lines[3]];
  expect(verifyChain(swapped.join('\n')).firstBadLine).toBe(2);
});

test('an empty log is not a verified log', () => {
  expect(verifyChain('').ok).toBe(false);
});

test('floats are refused rather than hashed differently from Python', () => {
  expect(() => canonicalJson({ x: 0.1 })).toThrow(/non-integer/);
});
