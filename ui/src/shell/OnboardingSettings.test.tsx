// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { expect, it, vi } from 'vitest';
import { Onboarding } from './Onboarding';
import { emptyDraft } from './firstRun';

it('awaits real settings persistence before summary, preserves failures for retry, and never claims protection', async () => {
  const user = userEvent.setup();
  let resolve!: () => void;
  const save = vi.fn().mockRejectedValueOnce(new Error('Hub unavailable')).mockImplementationOnce(() => new Promise<void>((r) => { resolve = r; }));
  const finish = vi.fn();
  render(<Onboarding apps={[]} initialStep={4} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub', ownerName: 'Owner', passkey: 'registered', backup: { destination: 'later', kitSaved: false } }} onSaveSettings={save} onFinish={finish} />);
  expect(screen.queryByRole('button', { name: /Download emergency kit/ })).toBeNull();
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Hub unavailable');
  expect(screen.queryByText('You are all set')).toBeNull();
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(screen.getByRole('button', { name: /Saving/ })).toBeDisabled();
  expect(finish).not.toHaveBeenCalled();
  await act(async () => resolve());
  expect(screen.getByRole('heading', { level: 2, name: 'You are all set' })).toBeInTheDocument();
  expect(screen.getByText(/does not enable backups/)).toBeInTheDocument();
  expect(screen.queryByText(/emergency kit saved/)).toBeNull();
  await user.click(screen.getByRole('button', { name: /Go to Home/ }));
  expect(finish).toHaveBeenCalledTimes(1);
});

it('offers only actual matching destinations and clears the binding when the choice changes', async () => {
  const user = userEvent.setup();
  const save = vi.fn().mockResolvedValue(undefined);
  render(<Onboarding apps={[]} initialStep={4} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} backupDestinations={[{ id: 'dst_0123456789abcdef', kind: 'usb', label: 'Existing disk' }, { id: 'dst_fedcba9876543210', kind: 's3', label: 'Bucket' }]} onSaveSettings={save} onFinish={() => {}} />);
  await user.selectOptions(screen.getByLabelText('Existing backup destination'), 'dst_0123456789abcdef');
  expect(screen.queryByRole('option', { name: 'Bucket' })).toBeNull();
  await user.click(screen.getByRole('radio', { name: /Decide later/ }));
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(save).toHaveBeenCalledWith(expect.objectContaining({ backup: { destination: 'later', destinationId: undefined, kitSaved: false } }));
});

it('places the backup recovery action inside the full-screen backup step', async () => {
  const recover = vi.fn();
  render(<Onboarding apps={[]} initialStep={4}
    backupRecoveryAction={<button type="button" onClick={recover}>Open recovery</button>}
    onSaveSettings={async () => {}} onFinish={() => {}} />);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Open recovery' }));
  expect(recover).toHaveBeenCalledOnce();
});

it('a wizard opened with an issued, unconfirmed kit can still skip it and finish, or re-issue', async () => {
  const user = userEvent.setup();
  const save = vi.fn().mockResolvedValue(undefined);
  const finish = vi.fn();
  const issue = vi.fn().mockResolvedValue({ groups: ['ABCD', 'EFGH', 'JKLM'], check: 'QRST', text: 'KIT', positions: [1, 3] });
  const kit = { state: 'issued' as const, positions: [2, 4], issue, confirm: vi.fn() };
  render(<Onboarding apps={[]} initialStep={4} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub', ownerName: 'Owner', passkey: 'registered', backup: { destination: 'later', kitSaved: false } }} kit={kit} onSaveSettings={save} onFinish={finish} />);
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(screen.getByRole('alert')).toHaveTextContent('Create and confirm your emergency kit first');
  await user.click(screen.getByRole('button', { name: /I lost my copy/ }));
  expect(await screen.findByLabelText('Owner recovery key')).toBeInTheDocument();
  expect(issue).toHaveBeenCalledTimes(1);
  await user.click(screen.getByRole('button', { name: 'Skip for now' }));
  await user.click(screen.getByRole('button', { name: /Finish setup/ }));
  expect(await screen.findByRole('heading', { level: 2, name: 'You are all set' })).toBeInTheDocument();
  expect(screen.getByText(/skipped for now/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Go to Home/ }));
  expect(finish).toHaveBeenCalledTimes(1);
});
it('continues from box name without creating another owner or requiring a passkey', async () => {
  render(<Onboarding apps={[]} ownerConfigured initial={{ boxName: 'home-hub', timeZone: 'UTC', ownerName: 'Dana' }} onSaveSettings={async () => {}} onFinish={() => {}} />);
  expect(screen.getByRole('heading', { name: 'Name your box' })).toBeVisible();
  await userEvent.setup().click(screen.getByRole('button', { name: 'Continue' }));
  expect(await screen.findByRole('heading', { name: 'Make it yours' })).toBeVisible();
  expect(screen.queryByRole('button', { name: 'Create the owner' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Create passkey' })).toBeNull();
});
