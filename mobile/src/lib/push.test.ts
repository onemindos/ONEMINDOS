// SPDX-License-Identifier: Apache-2.0
import type { UnifiedPushNative, UpEndpoint } from '../../modules/onemind-unifiedpush';
import { Features, OP } from '../api/client';
import { ApiError } from '../api/types';
import { v0Api } from '../test/fakes';
import {
  apnsTransport,
  disablePush,
  enablePush,
  loadPushRecord,
  parsePing,
  PushError,
  pushBlocker,
  rotateEndpoint,
  unifiedPushTransport,
} from './push';

type Listener = (e: never) => void;

function fakeUp(opts: { distributors?: string[]; saved?: string | null; answer?: 'endpoint' | 'fail' | 'silent'; last?: UpEndpoint | null } = {}) {
  const listeners = new Map<string, Listener[]>();
  const up = {
    registered: [] as Array<string | null>,
    distributors: () => opts.distributors ?? ['io.heckel.ntfy'],
    savedDistributor: () => (opts.saved === undefined ? 'io.heckel.ntfy' : opts.saved),
    saveDistributor: jest.fn(),
    useDefaultDistributor: jest.fn(async () => true),
    unregister: jest.fn(),
    lastEndpoint: () => opts.last ?? null,
    addListener: (ev: string, l: Listener) => {
      listeners.set(ev, [...(listeners.get(ev) ?? []), l]);
      return { remove: () => listeners.set(ev, (listeners.get(ev) ?? []).filter((x) => x !== l)) };
    },
    register(vapid: string | null) {
      up.registered.push(vapid);
      const emit = (ev: string, body: unknown) => (listeners.get(ev) ?? []).forEach((l) => l(body as never));
      if (opts.answer === 'fail') emit('onRegistrationFailed', { reason: 'ACTION_REQUIRED' });
      else if (opts.answer !== 'silent') emit('onNewEndpoint', { url: 'https://ntfy.box/upAbc', p256dh: 'pk', auth: 'au', temporary: false });
    },
  };
  return up as typeof up & UnifiedPushNative;
}

const allPush = new Features([OP.pushRegister, OP.vapidKey], 'openapi');

describe('UnifiedPush transport (Android)', () => {
  it('reports what blocks it', async () => {
    expect(await unifiedPushTransport(undefined).blocker()).toBe('no_module');
    expect(await unifiedPushTransport(fakeUp({ distributors: [] })).blocker()).toBe('no_distributor');
    expect(await unifiedPushTransport(fakeUp()).blocker()).toBeUndefined();
  });

  it('registers with the box VAPID key and returns the endpoint with its Web Push keys', async () => {
    const up = fakeUp();
    const h = await unifiedPushTransport(up).obtain('V'.repeat(87));
    expect(up.registered).toEqual(['V'.repeat(87)]);
    expect(h).toEqual({ platform: 'unifiedpush', endpoint: 'https://ntfy.box/upAbc', keys: { p256dh: 'pk', auth: 'au' } });
  });

  it('asks for the default distributor when none is saved, and fails clearly when none is chosen', async () => {
    const up = fakeUp({ saved: null });
    up.useDefaultDistributor.mockResolvedValueOnce(false);
    await expect(unifiedPushTransport(up).obtain()).rejects.toMatchObject({ blocker: 'no_distributor' });
  });

  it('passes on a distributor refusal, and falls back to the last endpoint when the event is missed', async () => {
    await expect(unifiedPushTransport(fakeUp({ answer: 'fail' })).obtain()).rejects.toThrow(/ACTION_REQUIRED/);
    const last = { url: 'https://ntfy.box/old', p256dh: null, auth: null, temporary: false };
    await expect(unifiedPushTransport(fakeUp({ answer: 'silent', last }), 10).obtain()).resolves.toEqual({ platform: 'unifiedpush', endpoint: 'https://ntfy.box/old' });
  });
});

describe('APNs transport (iPhone)', () => {
  const N = (over: Partial<Parameters<typeof apnsTransport>[0]> = {}) => ({
    getPermissionsAsync: jest.fn(async () => ({ granted: true, canAskAgain: true }) as never),
    requestPermissionsAsync: jest.fn(async () => ({ granted: true }) as never),
    getDevicePushTokenAsync: jest.fn(async () => ({ type: 'ios', data: 'a1b2c3' }) as never),
    unregisterForNotificationsAsync: jest.fn(async () => undefined),
    ...over,
  });

  it('sends the raw APNs token with its environment, never an Expo push token', async () => {
    const h = await apnsTransport(N(), true).obtain();
    expect(h).toMatchObject({ platform: 'apns', token: 'a1b2c3', environment: 'sandbox' });
    expect((await apnsTransport(N(), false).obtain()).environment).toBe('production');
  });

  it('is blocked when notifications were turned off for good', async () => {
    const n = N({ getPermissionsAsync: jest.fn(async () => ({ granted: false, canAskAgain: false }) as never) });
    expect(await apnsTransport(n).blocker()).toBe('no_permission');
    await expect(apnsTransport(n).obtain()).rejects.toBeInstanceOf(PushError);
  });
});

describe('registering push with the box', () => {
  const opts = { features: allPush, hubUrl: 'https://h', label: 'Pixel', deviceApproved: true, now: 0 };

  it('needs the hub route, and an approved device where the hub has a device registry', async () => {
    expect(await pushBlocker(unifiedPushTransport(fakeUp()), { features: Features.none(), deviceApproved: true })).toBe('hub_unsupported');
    const withDevices = new Features([OP.pushRegister, OP.deviceRequest], 'openapi');
    expect(await pushBlocker(unifiedPushTransport(fakeUp()), { features: withDevices, deviceApproved: false })).toBe('needs_device');
  });

  it('registers the endpoint, remembers it per hub, and turning off forgets it everywhere', async () => {
    const pushRegister = jest.fn(async (r: object) => ({ id: 'dev_push_1', ...r }) as never);
    const pushUnregister = jest.fn(async () => undefined);
    const api = v0Api({ pushRegister, pushUnregister, vapidPublicKey: async () => ({ key: 'K'.repeat(87) }) });
    const up = fakeUp();
    const rec = await enablePush(api, unifiedPushTransport(up), opts);
    expect(pushRegister).toHaveBeenCalledWith({
      platform: 'unifiedpush',
      endpoint: 'https://ntfy.box/upAbc',
      keys: { p256dh: 'pk', auth: 'au' },
      label: 'Pixel',
    });
    expect(up.registered).toEqual(['K'.repeat(87)]);
    expect(await loadPushRecord('https://h')).toEqual(rec);
    expect(await loadPushRecord('https://other')).toBeUndefined();
    await disablePush(api, unifiedPushTransport(up), rec);
    expect(pushUnregister).toHaveBeenCalledWith('dev_push_1');
    expect(up.unregister).toHaveBeenCalled();
    expect(await loadPushRecord('https://h')).toBeUndefined();
  });

  it('says the hub cannot push to iPhones when it refuses apns (no relay yet)', async () => {
    const pushRegister = jest.fn(async () => {
      throw new ApiError(422, 'conflict', 'apns needs the iOS relay');
    });
    const api = v0Api({ pushRegister });
    const N = {
      getPermissionsAsync: async () => ({ granted: true, canAskAgain: true }),
      requestPermissionsAsync: async () => ({ granted: true, canAskAgain: true }),
      getDevicePushTokenAsync: async () => ({ type: 'ios', data: 'a1b2c3' }),
      unregisterForNotificationsAsync: async () => undefined,
    } as never;
    await expect(enablePush(api, apnsTransport(N, true), opts)).rejects.toMatchObject({ blocker: 'hub_unsupported' });
  });

  it('re-registers when the distributor moves the endpoint', async () => {
    const pushRegister = jest.fn(async () => ({ id: 'reg2' }) as never);
    const pushUnregister = jest.fn(async () => undefined);
    const api = v0Api({ pushRegister, pushUnregister });
    const rec = { hubUrl: 'https://h', id: 'reg1', platform: 'unifiedpush' as const, handle: 'https://ntfy.box/a', since: '' };
    const next = await rotateEndpoint(api, rec, { url: 'https://ntfy.box/b', p256dh: null, auth: null, temporary: false }, 'Pixel');
    expect(pushUnregister).toHaveBeenCalledWith('reg1');
    expect(next).toMatchObject({ id: 'reg2', handle: 'https://ntfy.box/b' });
    expect(await rotateEndpoint(api, next, { url: 'https://ntfy.box/b', p256dh: null, auth: null, temporary: false }, 'Pixel')).toBe(next);
  });
});

describe('pings carry ids only (D-005)', () => {
  it('accepts an id and ignores anything that is not one', () => {
    expect(parsePing({ notification_id: 'ntf_01J9', box_id: 'b' })).toEqual({ id: 'ntf_01J9' });
    expect(parsePing({ opaque_id: 'abc' })).toEqual({ id: 'abc' });
    expect(parsePing({ notification_id: 'Your backup failed: disk full', box_id: 'b' })).toEqual({ id: undefined });
    expect(parsePing({ route: 'approvals' })).toBeUndefined();
    expect(parsePing(null)).toBeUndefined();
  });
});
