// SPDX-License-Identifier: Apache-2.0
// Settings → Push on Android: the three-step UnifiedPush guide (mobile/docs/push.md §3.1, issue #828).
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import type { ReactNode } from 'react';
import { Linking, Share } from 'react-native';
import type { UnifiedPushNative } from '../../modules/onemind-unifiedpush';
import { Features, OP } from '../api/client';
import type { Action, CatalogApp, PushRegistration } from '../api/types';
import { NTFY_FDROID, unifiedPushTransport } from '../lib/push';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import { deleteSecret, type Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { PushSection } from './PushSection';

const LIVE: Connection = { mode: 'live', hubUrl: 'https://onemind.local', token: 't' };
const VAPID = 'B'.repeat(87);
const NTFY: CatalogApp = {
  id: 'ntfy',
  name: 'ntfy',
  version: '2.37.2',
  description: 'Send push notifications',
  category: 'notifications',
  icon: 'icon.svg',
  license: 'Apache-2.0 OR GPL-2.0',
  source: 'https://github.com/binwiederhier/ntfy',
  archs: ['amd64', 'arm64'],
  requires: { gpu: false, minMemoryMb: 256 },
  web_port: 8080,
  installed: false,
  status: 'not_installed',
  links: { docs: null, github: null, website: null, support: null },
  tier: 'verified',
  scan: null,
};

type Listener = (e: never) => void;

/** The native module as the connector drives it: distributors, register(vapid), an endpoint event. */
function fakeUp(o: { distributors?: string[]; endpoint?: string } = {}) {
  const listeners = new Map<string, Listener[]>();
  const up = {
    registered: [] as Array<string | null>,
    distributors: () => o.distributors ?? ['io.heckel.ntfy'],
    savedDistributor: () => 'io.heckel.ntfy',
    saveDistributor: jest.fn(),
    useDefaultDistributor: jest.fn(async () => true),
    unregister: jest.fn(),
    lastEndpoint: () => null,
    lastPingAt: () => null,
    addListener: (ev: string, l: Listener) => {
      listeners.set(ev, [...(listeners.get(ev) ?? []), l]);
      return { remove: () => listeners.set(ev, (listeners.get(ev) ?? []).filter((x) => x !== l)) };
    },
    register(vapid: string | null) {
      up.registered.push(vapid);
      const url = o.endpoint ?? 'https://ntfy.onemind.local/upAbc';
      (listeners.get('onNewEndpoint') ?? []).forEach((l) => l({ url, p256dh: 'pk', auth: 'au', temporary: false } as never));
    },
  };
  return up as typeof up & UnifiedPushNative;
}

function Gate({ children }: { children: ReactNode }) {
  const s = useSession().session;
  return s && s.features.source !== 'unknown' ? children : null;
}

async function mount(o: { apps?: CatalogApp[]; actions?: Action[]; up?: ReturnType<typeof fakeUp>; conn?: Connection; regs?: PushRegistration[] } = {}) {
  const up = o.up ?? fakeUp();
  const regs: PushRegistration[] = o.regs ?? [];
  const api = v0Api({
    features: async () => new Features([OP.pushRegister, OP.vapidKey], 'openapi'),
    apps: async () => o.apps ?? [{ ...NTFY, installed: true, status: 'installed' }],
    actions: async () => o.actions ?? [],
    createAction: jest.fn(async (req) => ({ ...req, id: 'act_1', state: 'awaiting_approval' }) as Action),
    vapidPublicKey: jest.fn(async () => ({ key: VAPID })),
    pushRegister: jest.fn(async (req) => {
      const r = { id: 'dev_1', platform: req.platform, label: req.label, created_at: '2026-11-22T10:00:00Z' };
      regs.push(r);
      return r;
    }),
    pushRegistrations: jest.fn(async () => regs),
    pushUnregister: jest.fn(async () => undefined),
  });
  const deps: SessionDeps = { load: async () => o.conn ?? LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <PushSection deviceApproved phone={{ name: 'Pixel 9', installId: 'inst_pixel_9_000000000' }} os="android" transport={unifiedPushTransport(up)} />
      </Gate>
    </SessionProvider>,
  );
  return { api, up };
}

describe('Android push guide', () => {
  // The secure store is one in-memory map per test file: start every test with push off.
  beforeEach(() => deleteSecret('onemind.push.v1'));
  afterEach(() => jest.restoreAllMocks());

  it('with ntfy missing on the box, offers the install request and files exactly one app.install action', async () => {
    const { api } = await mount({ apps: [NTFY] });
    await fireEvent.press(await screen.findByTestId('push-ask-ntfy'));
    expect(await screen.findByText(/only after an owner approves it/)).toBeTruthy();
    expect(api.createAction).toHaveBeenCalledTimes(1);
    expect(api.createAction).toHaveBeenCalledWith(expect.objectContaining({ type: 'app.install', params: { app_id: 'ntfy' } }));
    // Filed once: the button is gone and push waits for the box.
    expect(screen.queryByTestId('push-ask-ntfy')).toBeNull();
    expect(screen.getByTestId('push-on')).toBeDisabled();
  });

  it('does not offer a second request while one waits in Approvals', async () => {
    const waiting = { type: 'app.install', params: { app_id: 'ntfy' }, id: 'act_0', state: 'awaiting_approval', idempotency_key: 'k', expires_at: '2026-11-23T00:00:00Z' } as Action;
    const { api } = await mount({ apps: [NTFY], actions: [waiting] });
    expect(await screen.findByText(/waits in Approvals/)).toBeTruthy();
    expect(screen.queryByTestId('push-ask-ntfy')).toBeNull();
    expect(api.createAction).not.toHaveBeenCalled();
  });

  it('with no distributor on the phone, shows the box ntfy address to copy, links to F-Droid and blocks Turn on', async () => {
    const share = jest.spyOn(Share, 'share').mockResolvedValue({ action: 'sharedAction' } as never);
    const open = jest.spyOn(Linking, 'openURL').mockResolvedValue(undefined);
    await mount({ up: fakeUp({ distributors: [] }) });
    expect(await screen.findByText('https://ntfy.onemind.local')).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId('push-on')).toBeDisabled());
    await fireEvent.press(screen.getByTestId('push-copy'));
    expect(share).toHaveBeenCalledWith({ message: 'https://ntfy.onemind.local' });
    await fireEvent.press(screen.getByTestId('push-get-ntfy'));
    expect(open).toHaveBeenCalledWith(NTFY_FDROID);
  });

  it('with both ready, Turn on registers platform unifiedpush with the Web Push keys and the box VAPID key, then shows the registration', async () => {
    const { api, up } = await mount();
    const on = await screen.findByTestId('push-on');
    await waitFor(() => expect(on).toBeEnabled());
    await fireEvent.press(on);
    expect(await screen.findByText(/Push is on/)).toBeTruthy();
    expect(up.registered).toEqual([VAPID]);
    expect(api.pushRegister).toHaveBeenCalledTimes(1);
    expect(api.pushRegister).toHaveBeenCalledWith({
      platform: 'unifiedpush',
      endpoint: 'https://ntfy.onemind.local/upAbc',
      keys: { p256dh: 'pk', auth: 'au' },
      label: 'Pixel 9',
    });
    expect(await screen.findByText('2026-11-22')).toBeTruthy();
    expect(screen.getByText('Pixel 9')).toBeTruthy();
    expect(screen.getByText('none yet')).toBeTruthy();
    expect(screen.getByTestId('push-off')).toBeTruthy();
  });

  it('warns when the endpoint is not on the box ntfy (the ntfy app still points at another server)', async () => {
    await mount({ up: fakeUp({ endpoint: 'https://ntfy.sh/upXyz' }) });
    const on = await screen.findByTestId('push-on');
    await waitFor(() => expect(on).toBeEnabled());
    await fireEvent.press(on);
    expect(await screen.findByText(/go through ntfy\.sh, not your box's ntfy/)).toBeTruthy();
  });

  it('shows nothing in the demo (no box)', async () => {
    await mount({ conn: { mode: 'mock', token: 'demo' } });
    await waitFor(() => expect(screen.queryByText(/demo/i)).toBeNull());
    expect(screen.queryByTestId('push')).toBeNull();
  });
});
