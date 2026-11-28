// SPDX-License-Identifier: Apache-2.0
// The mixed first run (founder pick 2026-11-28): Your place, the address step (offline first, the
// gateway saves the first site) and You decide (a practice that calls no API).
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Onboarding } from './Onboarding';
import { ONBOARDING_STEPS, emptyDraft } from './firstRun';

const at = (id: string) => ONBOARDING_STEPS.findIndex((s) => s.id === id);
const network = vi.fn(() => Promise.reject(new Error('no network in this test')));
beforeEach(() => { network.mockClear(); vi.stubGlobal('fetch', network); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });

function connected(extra: Partial<Parameters<typeof Onboarding>[0]> = {}) {
  const save = vi.fn().mockResolvedValue('saved' as const);
  render(<Onboarding apps={[]} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} onSaveSettings={vi.fn()} onSaveLocation={save} onFinish={vi.fn()} {...extra} />);
  return save;
}

it('names the place, finds no street address offline without sending it anywhere, then saves the position the owner gave', async () => {
  const user = userEvent.setup();
  const device = vi.fn().mockResolvedValue({ lat: 40.71281234, lon: -74.00601234 });
  const save = connected({ deviceLocation: device });
  await user.type(screen.getByLabelText('Place name'), 'Rivera Home');
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(screen.getByRole('heading', { level: 2, name: 'Where is your place?' })).toHaveFocus();

  await user.type(screen.getByLabelText('Your address'), '12 Orchard Lane, Springfield');
  await user.click(screen.getByRole('button', { name: /Find it on this box/ }));
  expect(screen.getByText(/no address index yet/)).toHaveTextContent('Nothing was sent anywhere.');
  expect(network).not.toHaveBeenCalled();

  expect(screen.getByText(/Some browsers ask their maker’s online location service; OneMind does not/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Use this device’s location/ }));
  expect(await screen.findByText(/Your map moved to 40\.71281° N, 74\.00601° W/)).toBeInTheDocument();
  expect(screen.getByText(/from this device’s location/)).toBeInTheDocument();

  await user.click(screen.getByRole('button', { name: /Save my place/ }));
  expect(save).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({
    placeName: 'Rivera Home', address: '12 Orchard Lane, Springfield', location: { lat: 40.712812, lon: -74.006012, source: 'device' },
  }));
  expect(await screen.findByRole('heading', { level: 2, name: 'AI can ask. Only you approve.' })).toHaveFocus();
  await user.click(screen.getByRole('button', { name: 'Back' }));
  expect(await screen.findByText(/Saved on this box as your first place/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Skip' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Continue' }));
  expect(save).toHaveBeenCalledTimes(1);
  expect(network).not.toHaveBeenCalled();
});

it('keeps the owner on the step with the reason when the gateway refuses the place, and Skip saves nothing', async () => {
  const user = userEvent.setup();
  const save = vi.fn().mockRejectedValueOnce(new Error('Only an owner can write map records'));
  render(<Onboarding apps={[]} initialStep={at('address')} initial={{ ...emptyDraft('UTC'), boxName: 'home-hub' }} onSaveSettings={vi.fn()} onSaveLocation={save} deviceLocation={undefined} onFinish={vi.fn()} />);
  await user.type(screen.getByLabelText('Coordinates'), 'https://www.openstreetmap.org/#map=17/41.8902/12.4922');
  await user.click(screen.getByRole('button', { name: /Move my map here/ }));
  expect(screen.getByText(/from a map link you pasted/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Save my place/ }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Only an owner can write map records');
  expect(screen.getByRole('heading', { level: 2, name: 'Where is your place?' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Skip' }));
  expect(await screen.findByRole('heading', { level: 2, name: 'AI can ask. Only you approve.' })).toBeInTheDocument();
  expect(save).toHaveBeenCalledTimes(1);
});

it('refuses coordinates the gateway would refuse, with the reason in the card', async () => {
  const user = userEvent.setup();
  connected({ initialStep: at('address'), deviceLocation: undefined });
  expect(screen.queryByRole('button', { name: /Use this device’s location/ })).toBeNull();
  await user.type(screen.getByLabelText('Coordinates'), '0, 0');
  await user.click(screen.getByRole('button', { name: /Move my map here/ }));
  expect(screen.getByText(/almost always a missing position/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Continue' })).toBeInTheDocument();
});

it('the practice is optional, calls no API, and moves focus to the result after an answer', async () => {
  const user = userEvent.setup();
  connected({ initialStep: at('decide') });
  expect(screen.getByText('Practice · simulated · nothing real moves')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Skip' })).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: 'Say no' }));
  expect(screen.getByText(/Practice done: you said no/).closest('p')).toHaveFocus();
  expect(screen.queryByRole('button', { name: 'Skip' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Try again' }));
  expect(screen.getByRole('button', { name: 'Hold to approve the practice request' })).toBeInTheDocument();
  expect(network).not.toHaveBeenCalled();
});

it('cannot hold? tap, wait, then confirm approves the practice', () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout', 'performance'] });
  connected({ initialStep: at('decide') });
  fireEvent.click(screen.getByRole('button', { name: 'Use confirmation instead' }));
  act(() => vi.advanceTimersByTime(2000));
  fireEvent.click(screen.getByRole('button', { name: 'Confirm approval' }));
  expect(screen.getByText(/Practice done: you approved it/)).toBeInTheDocument();
  expect(network).not.toHaveBeenCalled();
});
