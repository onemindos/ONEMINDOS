// SPDX-License-Identifier: Apache-2.0
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ApprovalCard } from './ApprovalCard';
import { HoldToApprove } from './HoldToApprove';
import { LEVEL_MEANING, LEVEL_NAME, VerificationBadge, type VerificationLevel } from './VerificationBadge';

beforeEach(() => vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] }));
afterEach(() => { cleanup(); vi.useRealTimers(); });

// WebAuthn reports only "the person was verified", never how (design 3.11): no level may name a method.
const MODALITY = /face|finger|touch|\bpin\b|passcode|iris|voice|retina/i;
const LEVELS: VerificationLevel[] = ['L0', 'L1', 'L2', 'L3'];

it.each(LEVELS)('names %s by number and word, with no claim about the check the device used', (level) => {
  const { container } = render(<VerificationBadge level={level} />);
  const badge = container.querySelector('.om-verify')!;
  expect(badge).toHaveTextContent(`${level} · ${LEVEL_NAME[level]}`);
  expect(badge.textContent).not.toMatch(MODALITY);
  expect(badge.getAttribute('title')).not.toMatch(MODALITY);
  expect(LEVEL_MEANING[level]).not.toMatch(MODALITY);
  expect(badge).toHaveAttribute('data-level', level);
});

it('marks levels with a shape as well as a colour', () => {
  const marks = LEVELS.map((l) => render(<VerificationBadge level={l} />).container.querySelector('.om-verify-mark')!.textContent);
  expect(new Set(marks).size).toBe(4);
});

it('says Needs for a requirement', () => {
  render(<VerificationBadge level="L2" required />);
  expect(screen.getByText('Needs L2 · Proven key')).toBeInTheDocument();
});

it('a short pointer press never approves, and the hold shows the level it needs', () => {
  const approve = vi.fn();
  render(<HoldToApprove label="Hold to approve the restore" requiredLevel="L2" onApprove={approve} />);
  const hold = screen.getByRole('button', { name: 'Hold to approve the restore' });
  fireEvent(hold, new MouseEvent('pointerdown', { bubbles: true, button: 0 }));
  act(() => vi.advanceTimersByTime(500));
  fireEvent(hold, new MouseEvent('pointerup', { bubbles: true, button: 0 }));
  act(() => vi.advanceTimersByTime(3000));
  fireEvent.click(hold); // a click is a short press too
  act(() => vi.advanceTimersByTime(3000));
  expect(approve).not.toHaveBeenCalled();
  expect(screen.getByText('Needs L2 · Proven key')).toBeInTheDocument();
});

it('the approval card shows the level an approval needs', () => {
  const now = Date.parse('2026-11-25T12:00:00Z');
  render(<ApprovalCard now={now} canDecide={{ allowed: true }} onApprove={() => {}} onDeny={() => {}}
    action={{ id: 'a1', type: 'backup.restore', params: { target: 'photos' }, state: 'awaiting_approval',
      expires_at: '2026-11-25T13:00:00Z', required_level: 'L2' }} />);
  expect(screen.getByText('Needs L2 · Proven key')).toBeInTheDocument();
});
