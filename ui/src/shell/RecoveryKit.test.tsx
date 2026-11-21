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

it('an already issued kit cannot be re-issued; the owner types groups from the saved copy', () => {
  render(<RecoveryKit kit={make({ state: 'issued', positions: [2, 4] })} onConfirmed={() => {}} />);
  expect(screen.queryByRole('button', { name: /Create my emergency kit/ })).toBeNull();
  expect(screen.getByLabelText('Group 2')).toBeInTheDocument();
});
