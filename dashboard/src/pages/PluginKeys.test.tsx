// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import { beforeEach, expect, it, vi } from 'vitest';
import { PluginKeys } from './PluginKeys';

const h = vi.hoisted(() => ({ load: vi.fn(), request: vi.fn(), revoke: vi.fn(), signOut: vi.fn(), available: true }));
vi.mock('../session', () => ({ useSignedIn: () => ({ api: h.available ? {
  pluginSigningKeys: h.load, requestPluginSigningKey: h.request, revokePluginSigningKey: h.revoke,
} : {} }), useSession: () => ({ signOut: h.signOut }) }));
vi.mock('../data/hub', () => ({ useHub: () => ({ now: Date.parse('2026-11-20T12:00:00Z') }),
  errorText: (error: Error) => ({ code: 'error', message: error.message }) }));
vi.mock('./parts', async () => ({ ...(await vi.importActual<typeof import('./parts')>('./parts')),
  useRun: () => async (job: () => Promise<unknown>) => job() }));

beforeEach(() => {
  h.available = true;
  h.load.mockReset().mockResolvedValue({ keys: [] });
  h.request.mockReset().mockResolvedValue({ id: 'action-enroll', state: 'awaiting_approval' });
  h.revoke.mockReset().mockResolvedValue({ id: 'action-revoke', state: 'awaiting_approval' });
});
// Test-only public Ed25519 fixture; no private key is committed.
const publicKey = "-----BEGIN PUBLIC KEY-----\nMCowBQYDK2VwAyEAFISlZ5bfwRok7YoZMnXfrM+k8IB2XGwPz4Gy9ZSQkhI=\n-----END PUBLIC KEY-----\n";
const show = () => render(<MemoryRouter><PluginKeys /></MemoryRouter>);

it('requests enrollment and shows pending approval without claiming an active key', async () => {
  show();
  await screen.findByText('No signing keys have been enrolled.');
  fireEvent.change(screen.getByLabelText('Key label'), { target: { value: 'My signing key' } });
  fireEvent.change(screen.getByLabelText('Public key PEM'), { target: { value: publicKey } });
  fireEvent.click(screen.getByRole('button', { name: 'Request enrollment' }));
  await screen.findByText(/Request action-enroll was filed/);
  expect(h.request).toHaveBeenCalledWith(expect.objectContaining({ name: 'My signing key', idempotency_key: expect.any(String) }));
  expect(screen.getByRole('link', { name: 'Review the fingerprint in Approvals' })).toHaveAttribute('href', '/approvals');
  expect(screen.getByText('No signing keys have been enrolled.')).toBeInTheDocument();
});

it('refuses private PEM before sending it to the gateway', async () => {
  show();
  await screen.findByLabelText('Public key PEM');
  fireEvent.change(screen.getByLabelText('Key label'), { target: { value: 'Mistaken input' } });
  fireEvent.change(screen.getByLabelText('Public key PEM'), { target: { value: '-----BEGIN PRIVATE KEY-----' } });
  expect(screen.getByRole('alert')).toHaveTextContent('Private keys are not accepted');
  expect(screen.getByRole('button', { name: 'Request enrollment' })).toBeDisabled();
  expect(h.request).not.toHaveBeenCalled();
});

it('requests revocation without changing displayed trust before approval', async () => {
  h.load.mockResolvedValue({ keys: [{ id: 'sha256:' + '1'.repeat(64), name: 'Enrolled key', active: true }] });
  show();
  fireEvent.click(await screen.findByRole('button', { name: 'Request revocation' }));
  await screen.findByText(/Request action-revoke was filed/);
  expect(h.revoke).toHaveBeenCalledTimes(1);
  expect(screen.getByText(/Active/)).toBeInTheDocument();
});

it('does not invent trust data or controls when the gateway API is unavailable', () => {
  h.available = false;
  show();
  expect(screen.getByText('Connect to a gateway to manage plugin signing trust')).toBeInTheDocument();
  expect(h.load).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Public key PEM')).not.toBeInTheDocument();
});
