// SPDX-License-Identifier: Apache-2.0
// Settings → My devices (#715) against a fake gateway: the list, Lost this device, and the hub's refusals.
import { fireEvent, render, screen } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Features, OP } from '../api/client';
import { ApiError, type MyDevice, type MyDevices } from '../api/types';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { DeviceSection, holds } from './DeviceSection';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const ME = { principal: { id: 'u1', kind: 'person' as const, role: 'owner' as const }, token: null, session: null, passkeys: 1, capabilities: ['can_approve', 'can_request'] };
const ago = (s: number) => new Date(Date.now() - s * 1000).toISOString();
const cred = (source: MyDevice['credentials'][number]['source'], id: string) => ({ source, id, label: 'x', detail: '', created_at: ago(9000), last_seen_at: null });

const THIS: MyDevice = { id: 'mdv_this', label: 'Pixel 9', kind: 'phone', current: true, last_seen_at: ago(5), first_seen_at: ago(9000), credentials: [cred('sessions', 's1'), cred('push', 'p1')] };
const LOST: MyDevice = { id: 'mdv_lost', label: 'Old tablet', kind: 'app', current: false, last_seen_at: ago(7200), first_seen_at: ago(90000), credentials: [cred('sessions', 's2'), cred('sessions', 's3'), cred('passkeys', 'k1')] };
const SOURCES = { sessions: true, passkeys: true, approver_keys: true, push: true, mesh: false, nats: false };

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(ops: string[], over: Parameters<typeof v0Api>[0]) {
  const api = v0Api({ features: async () => new Features(ops, 'openapi'), me: async () => ME, actions: async () => [], ...over });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <DeviceSection link={undefined} onLink={() => undefined} name="Pixel 9" onName={() => undefined} />
      </Gate>
    </SessionProvider>,
  );
  return api;
}

const BOTH = [OP.me, OP.myDevices, OP.myDeviceRemove];

describe('My devices', () => {
  it('lists each device with its kind, last seen and what it holds; the phone in hand has no Lost button', async () => {
    await mount(BOTH, { myDevices: async (): Promise<MyDevices> => ({ devices: [THIS, LOST], sources: SOURCES }) });
    expect(await screen.findByText('Old tablet')).toBeTruthy();
    expect(screen.getByText('In use here')).toBeTruthy();
    expect(screen.getByText('App')).toBeTruthy();
    expect(screen.getByText('2h ago')).toBeTruthy();
    expect(screen.getByText('2 sign-ins, 1 passkey')).toBeTruthy();
    expect(screen.getByTestId('my-device-lost-mdv_lost')).toBeTruthy();
    expect(screen.queryByTestId('my-device-lost-mdv_this')).toBeNull();
  });

  it('Lost this device asks once more, then removes it in one call and shows the list again', async () => {
    let list = [THIS, LOST];
    const removeMyDevice = jest.fn(async (id: string) => {
      list = list.filter((d) => d.id !== id);
      return { id, removed: true, revoked: { sessions: 2, passkeys: 1, approver_keys: 0, push: 0 } };
    });
    await mount(BOTH, { myDevices: async () => ({ devices: list, sources: SOURCES }), removeMyDevice });
    await fireEvent.press(await screen.findByTestId('my-device-lost-mdv_lost'));
    expect(removeMyDevice).not.toHaveBeenCalled(); // the first tap only asks
    expect(screen.getByText(/Remove Old tablet\?/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('my-device-confirm-mdv_lost'));
    expect(await screen.findByText(/Old tablet is removed: 3 credentials revoked/)).toBeTruthy();
    expect(removeMyDevice).toHaveBeenCalledTimes(1);
    expect(removeMyDevice).toHaveBeenCalledWith('mdv_lost');
    expect(screen.queryByTestId('my-device-mdv_lost')).toBeNull();
  });

  it('says plainly when the hub wants a fresh passkey or refuses the last owner passkey', async () => {
    const removeMyDevice = jest
      .fn()
      .mockRejectedValueOnce(new ApiError(401, 'unauthenticated', 'sign in again', { reason: 'step_up_required' }))
      .mockRejectedValueOnce(new ApiError(409, 'conflict', 'last owner passkey', { reason: 'last_owner' }));
    await mount(BOTH, { myDevices: async () => ({ devices: [THIS, LOST], sources: SOURCES }), removeMyDevice });
    await fireEvent.press(await screen.findByTestId('my-device-lost-mdv_lost'));
    await fireEvent.press(screen.getByTestId('my-device-confirm-mdv_lost'));
    expect(await screen.findByText(/your passkey before removing this device/)).toBeTruthy();
    await fireEvent.press(screen.getByTestId('my-device-confirm-mdv_lost'));
    expect(await screen.findByText(/last owner passkey on the box/)).toBeTruthy();
    expect(screen.getByTestId('my-device-mdv_lost')).toBeTruthy(); // still listed: nothing was removed
  });

  it('is not shown on a hub that does not serve /v1/me/devices', async () => {
    const myDevices = jest.fn();
    await mount([OP.me], { myDevices });
    expect(await screen.findByText('This phone')).toBeTruthy();
    expect(screen.queryByText('My devices')).toBeNull();
    expect(myDevices).not.toHaveBeenCalled();
  });

  it('counts what a device holds in words', () => {
    expect(holds(LOST)).toBe('2 sign-ins, 1 passkey');
    expect(holds({ ...LOST, credentials: [] })).toBe('nothing');
  });
});
