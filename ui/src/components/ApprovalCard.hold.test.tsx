// SPDX-License-Identifier: Apache-2.0
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { ApprovalCard, type ActionSummary } from './ApprovalCard';

afterEach(cleanup);
const now = Date.now();
const action: ActionSummary = {
  id: 'a1', type: 'backup.restore', params: {}, state: 'awaiting_approval',
  expires_at: new Date(now + 3600_000).toISOString(), created_at: new Date(now).toISOString(),
  hold: { duration: 2000 },
};

it('a hold card shows Hold to approve instead of Approve, and a click or short press does not approve', () => {
  const onApprove = vi.fn();
  render(<ApprovalCard action={action} now={now} canDecide={{ allowed: true }} onApprove={onApprove} onDeny={vi.fn()} />);
  expect(screen.queryByRole('button', { name: /^Approve / })).toBeNull();
  const hold = screen.getByRole('button', { name: /^Hold to approve/ });
  expect(hold).toBeEnabled();
  fireEvent.click(hold);
  fireEvent.keyDown(hold, { key: ' ' });
  fireEvent.keyUp(hold, { key: ' ' });
  expect(onApprove).not.toHaveBeenCalled();
});

it('while busy the fallback Approve button is disabled for a hold card and cannot approve', () => {
  const onApprove = vi.fn();
  render(<ApprovalCard action={action} now={now} canDecide={{ allowed: true }} busy onApprove={onApprove} onDeny={vi.fn()} />);
  const approve = screen.getByRole('button', { name: /^Approve / });
  expect(approve).toBeDisabled();
  fireEvent.click(approve);
  expect(onApprove).not.toHaveBeenCalled();
});

it('a viewer who may not decide gets no hold control, only a disabled Approve', () => {
  render(<ApprovalCard action={action} now={now} canDecide={{ allowed: false, reason: 'Only the owner' }} onApprove={vi.fn()} onDeny={vi.fn()} />);
  expect(screen.queryByRole('button', { name: /^Hold to approve/ })).toBeNull();
  expect(screen.getByRole('button', { name: /^Approve / })).toBeDisabled();
});
