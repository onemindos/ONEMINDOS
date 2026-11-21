// SPDX-License-Identifier: Apache-2.0
import type { Action } from '../api/types';
import { asksParent, limitsText, roleLabel, ROLES, summarizeAgents } from './people';

const act = (id: string, by: string, state: Action['state'], at: string, extra: Partial<Action> = {}): Action => ({
  id, type: 'app.install', params: { app_id: 'x' }, idempotency_key: 'k', expires_at: '', state, created_at: at, requested_by: { id: by, kind: 'agent' }, ...extra,
});

describe('people helpers', () => {
  it('knows the five roles and who must ask a parent', () => {
    expect(ROLES).toEqual(['owner', 'adult', 'teen', 'child', 'guest']);
    expect(asksParent('teen') && asksParent('child')).toBe(true);
    expect(asksParent('adult') || asksParent('guest') || asksParent(undefined)).toBe(false);
    expect(roleLabel('teen')).toBe('Teen');
    expect(roleLabel('wizard')).toBe('Unknown (wizard)');
  });
  it('words limits plainly', () => {
    expect(limitsText(undefined)).toBe('No limits set.');
    expect(limitsText({ max_age_rating: 12, allowed_apps: ['a', 'b'], blocked_tags: ['chat'], windows: [] })).toBe(
      'apps rated above 12 are hidden; 2 allowed apps; blocked: chat; no allowed hours.',
    );
  });
  it('summarises agents from asks and token scopes', () => {
    const rows = summarizeAgents(
      [
        act('1', 'agent:hermes', 'awaiting_approval', '2026-11-21T10:00:00Z'),
        act('2', 'agent:hermes', 'succeeded', '2026-11-21T09:00:00Z'),
        act('3', 'agent:hermes', 'cancelled', '2026-11-21T08:00:00Z', { decided_by: { id: 'o', kind: 'person' } }),
        { ...act('4', 'alex', 'succeeded', '2026-11-21T07:00:00Z'), requested_by: { id: 'alex', kind: 'person' } },
      ],
      [{ id: 't', name: 'h', principal_id: 'agent:hermes', kind: 'agent', scopes: ['apps:read', 'actions:request'] }],
    );
    expect(rows).toHaveLength(1);
    expect(rows[0]).toMatchObject({ id: 'agent:hermes', asks: 3, waiting: 1, approved: 1, denied: 1, scopes: ['actions:request', 'apps:read'] });
    expect(rows[0]!.recent.map((r) => r.id)).toEqual(['1', '2', '3']);
  });
  it('lists a token-only agent with no asks', () => {
    expect(summarizeAgents([], [{ id: 't', name: 'h', principal_id: 'agent:a', kind: 'agent', scopes: [] }])).toHaveLength(1);
  });
});
