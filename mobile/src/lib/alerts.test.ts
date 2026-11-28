// SPDX-License-Identifier: Apache-2.0
import { makeActions, makeInbox, makeNodes } from '../api/fixtures';
import type { Action, NodeRecord } from '../api/types';
import { diffAlerts, inboxAlerts, snapshot } from './alerts';

const NOW = Date.parse('2026-11-12T12:00:00Z');

describe('diffAlerts', () => {
  const actions = makeActions(NOW);
  const nodes = makeNodes(NOW);

  it('raises nothing on the first poll', () => {
    expect(diffAlerts(undefined, snapshot(actions, nodes), actions, nodes)).toEqual([]);
  });

  it('raises nothing when nothing changed', () => {
    const s = snapshot(actions, nodes);
    expect(diffAlerts(s, s, actions, nodes)).toEqual([]);
  });

  it('alerts on a new pending request, naming the requester kind', () => {
    const prev = snapshot([], nodes);
    const fresh: Action = { ...actions[0]!, id: 'act-9', state: 'awaiting_approval' };
    const out = diffAlerts(prev, snapshot([fresh], nodes), [fresh], nodes);
    expect(out).toEqual([
      expect.objectContaining({ title: 'Approval needed', body: 'agent ops-agent asks: Install ollama', route: 'approvals' }),
    ]);
  });

  it('alerts when an action finishes', () => {
    const a = { ...actions[0]!, state: 'succeeded' as const, result: { outcome: 'succeeded', message: 'applied' } };
    const out = diffAlerts(snapshot(actions, nodes), snapshot([a], nodes), [a], nodes);
    expect(out[0]).toMatchObject({ title: 'Install ollama: succeeded', body: 'applied', route: 'activity' });
  });

  it('alerts on offline and recovery, not on online/stale flaps', () => {
    const flip = (status: NodeRecord['status']) => nodes.map((n) => (n.hostname === 'hub' ? { ...n, status } : n));
    const s0 = snapshot(actions, nodes);
    expect(diffAlerts(s0, snapshot(actions, flip('stale')), actions, flip('stale'))).toEqual([]);
    const off = diffAlerts(s0, snapshot(actions, flip('offline')), actions, flip('offline'));
    expect(off).toEqual([expect.objectContaining({ title: 'Node offline', route: 'nodes' })]);
    const back = diffAlerts(snapshot(actions, flip('offline')), s0, actions, nodes);
    expect(back).toEqual([expect.objectContaining({ title: 'Node back' })]);
  });
});

it('classifies inbox alerts by the approval topic rather than the action ID', () => {
  const approval = makeInbox(NOW, 'owner')[0]!;
  const succeeded = { ...approval, id: 'ntf-succeeded', topic: 'apps', title: 'Done' };
  const failed = { ...approval, id: 'ntf-failed', topic: 'apps', title: 'Failed' };
  const [waiting, done, error] = inboxAlerts(new Set(), [approval, succeeded, failed]);
  expect(waiting).toMatchObject({ route: 'approvals', actionId: approval.action_id });
  expect(done).toMatchObject({ route: 'inbox', actionId: undefined });
  expect(error).toMatchObject({ route: 'inbox', actionId: undefined });
});
