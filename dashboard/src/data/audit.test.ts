// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from 'vitest';
import type { AuditRecord } from '../api/wiring';
import { auditKind, toActivity, toAuditEntry } from './audit';

const rec = (over: Partial<AuditRecord>): AuditRecord => ({ seq: 1, ts: '2026-11-12T10:00:00Z', event: 'action.requested', principal: { id: 'ops', kind: 'agent' }, action_id: 'a1', data: { type: 'app.install' }, hash: 'abcdef0123456789', prev_hash: '0'.repeat(64), ...over });

describe('audit adapters', () => {
  it('classifies events', () => {
    expect(auditKind('auth.login.succeeded')).toBe('sign-in');
    expect(auditKind('action.requested')).toBe('request');
    expect(auditKind('action.approved')).toBe('decision');
    expect(auditKind('action.succeeded')).toBe('result');
    expect(auditKind('audit.checkpoint')).toBe('checkpoint');
    expect(auditKind('user.created')).toBe('config');
  });
  it('keeps the actor kind, shortens the hash, shows only short scalars', () => {
    const e = toAuditEntry(rec({ data: { type: 'app.install', long: 'x'.repeat(200), nested: { a: 1 } } }));
    expect(e.actor).toMatchObject({ id: 'ops', kind: 'agent' });
    expect(e.hash).toBe('abcdef01');
    expect(e.text).toBe('action.requested (type: app.install)');
  });
  it('a record with no principal is the system; unknown kinds fall back to system', () => {
    expect(toAuditEntry(rec({ principal: null })).actor).toEqual({ id: 'system', kind: 'system' });
    expect(toAuditEntry(rec({ principal: { id: 'x', kind: 'weird' } })).actor.kind).toBe('system');
  });
  it('lists newest first and reports a broken chain', () => {
    const a = toActivity([rec({ seq: 1 }), rec({ seq: 2 })], { ok: false, records: 2, first_bad_seq: 2, head: { seq: 2, hash: 'h' }, checked_at: 'now', reason: 'x' });
    expect(a.entries.map((e) => e.seq)).toEqual([2, 1]);
    expect(a.verify).toMatchObject({ state: 'broken', broken_at: 2, last: 2 });
  });
});
