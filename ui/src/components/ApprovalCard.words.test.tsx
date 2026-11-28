// SPDX-License-Identifier: Apache-2.0
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { ApprovalsBoard } from '../settings/ApprovalsBoard';
import { ACTION_WORDS, ApprovalCard, actionTitle, actionWords, type ActionSummary } from './ApprovalCard';

afterEach(cleanup);
const now = Date.now();
const base: ActionSummary = { id: 'a1', type: 'backup.destination.add', params: {}, state: 'awaiting_approval', expires_at: new Date(now + 3600_000).toISOString(), created_at: new Date(now).toISOString() };

it('says a known action type in plain words, with the target when there is one', () => {
  expect(actionTitle(base)).toBe('Add a backup destination');
  expect(actionTitle({ type: 'app.install', params: {}, target_name: 'Ollama' })).toBe('Install Ollama');
});

it('reads an unknown type as spaced words, never the dotted name', () => {
  expect(actionWords('widget.frob_nicate')).toBe('Widget frob nicate');
  expect(actionWords('')).toBe('A request');
  expect(actionTitle({ type: 'widget.frob', params: { node_id: 'n1' } })).toBe('Widget frob n1');
});

it('no label in the table is a dotted name', () => {
  for (const [type, words] of Object.entries(ACTION_WORDS)) expect(words, type).not.toMatch(/\w\.\w/);
});

it('the card shows the display name when given and the id when not', () => {
  render(<ApprovalCard action={{ ...base, requested_by: { id: 'usr_8f2c', kind: 'person', name: 'Alex' }, decided_by: { id: 'usr_9', kind: 'person' } }} now={now} canDecide={{ allowed: true }} />);
  expect(screen.getByText('Alex')).toBeInTheDocument();
  expect(screen.queryByText('usr_8f2c')).toBeNull();
  cleanup();
  render(<ApprovalCard action={{ ...base, requested_by: { id: 'usr_8f2c', kind: 'person' } }} now={now} canDecide={{ allowed: true }} />);
  expect(screen.getByText('usr_8f2c')).toBeInTheDocument();
});

it('the card shows who decided by name, and by id when there is no name', () => {
  const decided = { ...base, state: 'succeeded' as const, requested_by: { id: 'usr_a1', kind: 'person' as const, name: 'Alex' } };
  render(<ApprovalCard action={{ ...decided, decided_by: { id: 'usr_o9', kind: 'person', name: 'Zeus' } }} now={now} canDecide={{ allowed: true }} />);
  expect(screen.getByText('Zeus')).toBeInTheDocument();
  expect(document.body.textContent).not.toContain('usr_o9');
  cleanup();
  render(<ApprovalCard action={{ ...decided, decided_by: { id: 'usr_o9', kind: 'person' } }} now={now} canDecide={{ allowed: true }} />);
  expect(screen.getByText('usr_o9')).toBeInTheDocument();
});

it('Recent decisions shows both people by name and no usr_ id', () => {
  const row: ActionSummary = { ...base, id: 'd1', state: 'succeeded', requested_by: { id: 'usr_a1', kind: 'person', name: 'Alex' }, decided_by: { id: 'usr_o9', kind: 'person', name: 'Zeus' } };
  const unnamed: ActionSummary = { ...row, id: 'd2', decided_by: { id: 'usr_x7', kind: 'person' } };
  render(<ApprovalsBoard actions={{ status: 'ready', data: [], asOf: new Date(now).toISOString(), stale: false }} plans={{}} decided={[row]} now={now} canDecide={{ allowed: true }} />);
  const list = screen.getByRole('list', { name: 'Recent decisions' });
  expect(list).toHaveTextContent('Asked by Alex · decided by Zeus');
  expect(list.textContent).not.toMatch(/usr_/);
  cleanup();
  render(<ApprovalsBoard actions={{ status: 'ready', data: [], asOf: new Date(now).toISOString(), stale: false }} plans={{}} decided={[unnamed]} now={now} canDecide={{ allowed: true }} />);
  expect(screen.getByRole('list', { name: 'Recent decisions' })).toHaveTextContent('decided by usr_x7');
});
