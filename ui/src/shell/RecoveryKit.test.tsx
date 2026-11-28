// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { RecoveryKit, type OnboardingKit } from './RecoveryKit';

const issued = { groups: ['ABCD', 'EFGH', 'JKLM'], check: 'QRST', text: 'KIT', positions: [1, 3] };
const make = (over: Partial<OnboardingKit> = {}): OnboardingKit => ({ state: 'missing', positions: [], issue: vi.fn().mockResolvedValue(issued), confirm: vi.fn().mockResolvedValue(undefined), ...over });

it('shows the key once, requires the save before the type-back, and confirms two groups', async () => {
  const u = userEvent.setup();
  URL.createObjectURL = vi.fn(() => 'blob:x');
  URL.revokeObjectURL = vi.fn();
  const kit = make();
  const done = vi.fn();
  render(<RecoveryKit kit={kit} onConfirmed={done} />);
  await u.click(screen.getByRole('button', { name: /Create my emergency kit/ }));
  expect(await screen.findByLabelText('Owner recovery key')).toHaveTextContent('ABCD-EFGH-JKLM');
  expect(screen.queryByRole('button', { name: 'Confirm my kit' })).toBeNull();
  await u.click(screen.getByRole('button', { name: /Download emergency kit/ }));
  await u.type(screen.getByLabelText('Group 1'), 'abcd');
  await u.type(screen.getByLabelText('Group 3'), 'jklm');
  await u.click(screen.getByRole('button', { name: 'Confirm my kit' }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  expect(kit.confirm).toHaveBeenCalledWith({ '1': 'ABCD', '3': 'JKLM' });
  expect(screen.queryByLabelText('Owner recovery key')).toBeNull();
  expect(screen.getByRole('status')).toHaveTextContent('confirmed');
});

it('a wrong answer is shown and nothing is marked confirmed', async () => {
  const u = userEvent.setup();
  URL.createObjectURL = vi.fn(() => 'blob:x');
  URL.revokeObjectURL = vi.fn();
  const kit = make({ confirm: vi.fn().mockRejectedValue(new Error('those groups do not match your kit')) });
  const done = vi.fn();
  render(<RecoveryKit kit={kit} onConfirmed={done} />);
  await u.click(screen.getByRole('button', { name: /Create my emergency kit/ }));
  await u.click(await screen.findByRole('button', { name: /Download emergency kit/ }));
  await u.type(screen.getByLabelText('Group 1'), 'zzzz');
  await u.type(screen.getByLabelText('Group 3'), 'zzzz');
  await u.click(screen.getByRole('button', { name: 'Confirm my kit' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
  expect(done).not.toHaveBeenCalled();
});

it('an already issued kit can be re-issued when the copy is lost, then confirmed', async () => {
  const u = userEvent.setup();
  URL.createObjectURL = vi.fn(() => 'blob:x');
  URL.revokeObjectURL = vi.fn();
  const kit = make({ state: 'issued', positions: [2, 4] });
  const done = vi.fn();
  render(<RecoveryKit kit={kit} onConfirmed={done} />);
  expect(screen.queryByRole('button', { name: /Create my emergency kit/ })).toBeNull();
  expect(screen.getByLabelText('Group 2')).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: /I lost my copy/ }));
  expect(await screen.findByLabelText('Owner recovery key')).toHaveTextContent('ABCD-EFGH-JKLM');
  await u.click(screen.getByRole('button', { name: /Download emergency kit/ }));
  await u.type(screen.getByLabelText('Group 1'), 'abcd');
  await u.type(screen.getByLabelText('Group 3'), 'jklm');
  await u.click(screen.getByRole('button', { name: 'Confirm my kit' }));
  await waitFor(() => expect(done).toHaveBeenCalled());
});

it('replaces a confirmed kit and binds confirmation to the replacement page', async () => {
  const u = userEvent.setup();
  const print = vi.spyOn(window, 'print').mockImplementation(() => {});
  const fingerprint = '1122334455667788';
  const kit = make({ state: 'confirmed', fingerprint: '1234567890abcdef',
    issue: vi.fn().mockResolvedValue({ ...issued, fingerprint }) });
  const done = vi.fn();
  render(<RecoveryKit kit={kit} allowReplacement onConfirmed={done} />);
  await u.click(screen.getByRole('button', { name: 'Replace emergency kit' }));
  await screen.findByLabelText('Owner recovery key');
  expect(screen.queryByRole('button', { name: 'Confirm my kit' })).toBeNull();
  await u.click(screen.getByRole('button', { name: 'Print' }));
  expect(print).toHaveBeenCalledOnce();
  print.mockRestore();
  await u.type(screen.getByLabelText('Group 1'), 'abcd');
  await u.type(screen.getByLabelText('Group 3'), 'jklm');
  await u.click(screen.getByRole('button', { name: 'Confirm my kit' }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  expect(kit.confirm).toHaveBeenCalledWith({ '1': 'ABCD', '3': 'JKLM' }, fingerprint);
});

it('skip for now is offered while the kit is unconfirmed', async () => {
  const u = userEvent.setup();
  const skip = vi.fn();
  render(<RecoveryKit kit={make({ state: 'issued', positions: [2, 4] })} onConfirmed={() => {}} onSkip={skip} />);
  await u.click(screen.getByRole('button', { name: 'Skip for now' }));
  expect(skip).toHaveBeenCalled();
});

it('shows the disk recovery key beside the owner key when the box has one, and forgets both once confirmed', async () => {
  const u = userEvent.setup();
  URL.createObjectURL = vi.fn(() => 'blob:x');
  URL.revokeObjectURL = vi.fn();
  const kit = make({ issue: vi.fn().mockResolvedValue({ ...issued, disk_recovery_key: 'cbdefghi-jklnrtuv' }) });
  render(<RecoveryKit kit={kit} onConfirmed={vi.fn()} />);
  await u.click(screen.getByRole('button', { name: /Create my emergency kit/ }));
  expect(await screen.findByLabelText('Disk recovery key')).toHaveTextContent('cbdefghi-jklnrtuv');
  expect(screen.getByText(/rescue console/)).toBeInTheDocument();
  await u.click(screen.getByRole('button', { name: /Download emergency kit/ }));
  await u.type(screen.getByLabelText('Group 1'), 'abcd');
  await u.type(screen.getByLabelText('Group 3'), 'jklm');
  await u.click(screen.getByRole('button', { name: 'Confirm my kit' }));
  await waitFor(() => expect(screen.queryByLabelText('Disk recovery key')).toBeNull());
});

it('points at the earlier kit that holds the disk key when this one does not', async () => {
  const u = userEvent.setup();
  const kit = make({ issue: vi.fn().mockResolvedValue({ ...issued, disk_key_kit: { fingerprint: 'cafe1234cafe1234', issued_at: '2026-11-20T08:00:00Z' } }) });
  render(<RecoveryKit kit={kit} onConfirmed={vi.fn()} />);
  await u.click(screen.getByRole('button', { name: /Create my emergency kit/ }));
  await screen.findByLabelText('Owner recovery key');
  expect(screen.queryByLabelText('Disk recovery key')).toBeNull();
  expect(screen.getByRole('note')).toHaveTextContent(/not on this page.*2026-11-20T08:00:00Z.*cafe1234cafe1234/);
});

it('shows no disk key block on a box whose data disk is not encrypted', async () => {
  const u = userEvent.setup();
  render(<RecoveryKit kit={make()} onConfirmed={vi.fn()} />);
  await u.click(screen.getByRole('button', { name: /Create my emergency kit/ }));
  await screen.findByLabelText('Owner recovery key');
  expect(screen.queryByLabelText('Disk recovery key')).toBeNull();
});
