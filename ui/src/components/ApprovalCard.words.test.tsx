// SPDX-License-Identifier: Apache-2.0
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
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
