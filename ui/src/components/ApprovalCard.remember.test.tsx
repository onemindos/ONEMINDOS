// SPDX-License-Identifier: Apache-2.0
// "Approve and remember…" (gateway permissions design 3.6.1): offered only when the page asks for it,
// never on a card that needs a hold (physical), and disabled when the viewer may not decide.
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApprovalCard, type ActionSummary } from './ApprovalCard';

afterEach(cleanup);
const now = Date.now();
const action: ActionSummary = {
  id: 'a1', type: 'backup.run', params: {}, state: 'awaiting_approval',
  expires_at: new Date(now + 3600_000).toISOString(), created_at: new Date(now).toISOString(),
};

it('offers Approve and remember next to Approve and opens the sheet for this request', () => {
  const onRemember = vi.fn();
  render(<ApprovalCard action={action} now={now} canDecide={{ allowed: true }} onApprove={vi.fn()} onDeny={vi.fn()} onRemember={onRemember} />);
  fireEvent.click(screen.getByRole('button', { name: /^Approve and remember/ }));
  expect(onRemember).toHaveBeenCalledWith(action);
});

it('is absent without the handler and on a hold card, and disabled for a viewer who may not decide', () => {
  const { rerender } = render(<ApprovalCard action={action} now={now} canDecide={{ allowed: true }} onApprove={vi.fn()} onDeny={vi.fn()} />);
  expect(screen.queryByRole('button', { name: /^Approve and remember/ })).toBeNull();
  rerender(<ApprovalCard action={{ ...action, hold: { duration: 2000 } }} now={now} canDecide={{ allowed: true }} onApprove={vi.fn()} onDeny={vi.fn()} onRemember={vi.fn()} />);
  expect(screen.queryByRole('button', { name: /^Approve and remember/ })).toBeNull();
  rerender(<ApprovalCard action={action} now={now} canDecide={{ allowed: false, reason: 'Only the owner' }} onApprove={vi.fn()} onDeny={vi.fn()} onRemember={vi.fn()} />);
  expect(screen.getByRole('button', { name: /^Approve and remember/ })).toBeDisabled();
});
