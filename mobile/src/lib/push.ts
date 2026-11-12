// SPDX-License-Identifier: Apache-2.0
// Push while the app is closed (D-005, contract §12.14, CORE-MOBILE-4/-5), without a vendor reading
// the alerts: the box sends a content-free ping `{notification_id, box_id}`; the phone wakes and
// fetches the text from the box over HTTPS.
//
//   Android: UnifiedPush. The distributor is the ntfy app, pointed at the box's own ntfy server.
//            No Google Play Services, no Firebase.
//   iPhone:  APNs through the stateless OneMind relay (mobile/docs/push.md). The phone sends its raw
//            APNs device token to the box (never Expo's push service, which would add a third-party
//            cloud); the box asks the relay to ping it. The relay needs the founder's Apple
//            developer account (F-4).
import * as Notifications from 'expo-notifications';
import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { unifiedPush as defaultUp, type UnifiedPushNative, type UpEndpoint } from '../../modules/onemind-unifiedpush';
import { OP, type Features, type OneMindApi } from '../api/client';
import { ApiError, type PushRegistration, type PushRegistrationRequest } from '../api/types';
import { deleteSecret, loadSecret, saveSecret } from '../storage';

export type PushBlocker =
  | 'hub_unsupported' // the hub has no /v1/push/registrations yet
  | 'no_module' // this build has no native push module (Expo Go, tests, iOS for UnifiedPush)
  | 'no_distributor' // Android: no UnifiedPush distributor (the ntfy app) installed
  | 'no_permission' // the person turned notifications off for this app
  | 'needs_device'; // the hub registers push per approved device, and this phone is not approved yet

export class PushError extends Error {
  constructor(
    readonly blocker: PushBlocker | 'failed',
    message: string,
  ) {
    super(message);
    this.name = 'PushError';
  }
}

export type PushHandle = Omit<PushRegistrationRequest, 'label'>;

/** One way of getting an endpoint or token from the phone's push system. */
export interface PushTransport {
  platform: 'unifiedpush' | 'apns';
  blocker(): Promise<PushBlocker | undefined>;
  obtain(vapid?: string): Promise<PushHandle>;
  release(): Promise<void>;
}

const ENDPOINT_TIMEOUT_MS = 20_000;

/** Android: UnifiedPush through the native module (mobile/modules/onemind-unifiedpush). */
export function unifiedPushTransport(up: UnifiedPushNative | undefined = defaultUp, timeoutMs = ENDPOINT_TIMEOUT_MS): PushTransport {
  const handle = (e: UpEndpoint): PushHandle => ({
    platform: 'unifiedpush',
    endpoint: e.url,
    ...(e.p256dh && e.auth ? { keys: { p256dh: e.p256dh, auth: e.auth } } : {}),
  });
  return {
    platform: 'unifiedpush',
    async blocker() {
      if (!up) return 'no_module';
      if (up.distributors().length === 0) return 'no_distributor';
      return undefined;
    },
    async obtain(vapid) {
      if (!up) throw new PushError('no_module', 'UnifiedPush is not part of this build');
      if (!up.savedDistributor() && !(await up.useDefaultDistributor()))
        throw new PushError('no_distributor', 'No UnifiedPush distributor was chosen');
      return new Promise<PushHandle>((resolve, reject) => {
        const subs = [
          up.addListener('onNewEndpoint', (e) => done(() => resolve(handle(e)))),
          up.addListener('onRegistrationFailed', (e) => done(() => reject(new PushError('failed', `The distributor refused: ${e.reason}`)))),
        ];
        const timer = setTimeout(() => {
          const last = up.lastEndpoint();
          done(() => (last ? resolve(handle(last)) : reject(new PushError('failed', 'The distributor did not answer'))));
        }, timeoutMs);
        function done(fn: () => void) {
          clearTimeout(timer);
          subs.forEach((s) => s.remove());
          fn();
        }
        up.register(vapid ?? null);
      });
    },
    async release() {
      up?.unregister();
    },
  };
}

/** iPhone: the raw APNs device token (not an Expo push token). */
export function apnsTransport(N: Pick<typeof Notifications, 'getPermissionsAsync' | 'requestPermissionsAsync' | 'getDevicePushTokenAsync' | 'unregisterForNotificationsAsync'> = Notifications, dev = __DEV__): PushTransport {
  return {
    platform: 'apns',
    async blocker() {
      const p = await N.getPermissionsAsync();
      return !p.granted && !p.canAskAgain ? 'no_permission' : undefined;
    },
    async obtain() {
      let p = await N.getPermissionsAsync();
      if (!p.granted && p.canAskAgain) p = await N.requestPermissionsAsync();
      if (!p.granted) throw new PushError('no_permission', 'Notifications are off for OneMind');
      const t = await N.getDevicePushTokenAsync();
      if (t.type !== 'ios' || typeof t.data !== 'string') throw new PushError('failed', 'No APNs token from the system');
      return {
        platform: 'apns',
        token: t.data,
        // UNVERIFIED for ad-hoc builds: debug builds use the APNs sandbox, store and TestFlight builds production.
        environment: dev ? 'sandbox' : 'production',
        bundle_id: Constants.expoConfig?.ios?.bundleIdentifier,
      };
    },
    async release() {
      await N.unregisterForNotificationsAsync().catch(() => undefined);
    },
  };
}

export function platformTransport(os: string = Platform.OS): PushTransport | undefined {
  if (os === 'android') return unifiedPushTransport();
  if (os === 'ios') return apnsTransport();
  return undefined;
}

/** What this phone remembers about its registration with the box (secure store, per hub). */
export interface PushRecord {
  hubUrl: string;
  id: string;
  platform: 'unifiedpush' | 'apns';
  /** Endpoint or token as registered, so a rotated one is re-registered. */
  handle: string;
  since: string;
}

const KEY = 'onemind.push.v1';

export async function loadPushRecord(hubUrl: string): Promise<PushRecord | undefined> {
  try {
    const r = JSON.parse((await loadSecret(KEY)) ?? 'null') as PushRecord | null;
    return r && r.hubUrl === hubUrl && typeof r.id === 'string' ? r : undefined;
  } catch {
    return undefined;
  }
}

export interface EnableOpts {
  features: Features;
  hubUrl: string;
  label: string;
  /** The hub has a device registry (clients.md) and this phone is not approved yet. */
  deviceApproved: boolean;
  now?: number;
}

/** Why push cannot be turned on right now, checked before asking the OS for anything. */
export async function pushBlocker(t: PushTransport | undefined, o: Pick<EnableOpts, 'features' | 'deviceApproved'>): Promise<PushBlocker | undefined> {
  if (!o.features.has(OP.pushRegister)) return 'hub_unsupported';
  if (o.features.has(OP.deviceRequest) && !o.deviceApproved) return 'needs_device';
  if (!t) return 'no_module';
  return t.blocker();
}

/** Turn push on: get an endpoint/token, register it with the box, remember it. */
export async function enablePush(api: OneMindApi, t: PushTransport | undefined, o: EnableOpts): Promise<PushRecord> {
  const blocked = await pushBlocker(t, o);
  if (blocked || !t) throw new PushError(blocked ?? 'no_module', `Push is not available: ${blocked}`);
  const vapid = t.platform === 'unifiedpush' && o.features.has(OP.vapidKey) ? (await api.vapidPublicKey()).key : undefined;
  const h = await t.obtain(vapid);
  let reg: PushRegistration;
  try {
    reg = await api.pushRegister({ ...h, label: o.label });
  } catch (e) {
    // Today's hub refuses apns with 422 until its iOS relay ships (CORE-NOTIFY-4); say so plainly.
    if (h.platform === 'apns' && e instanceof ApiError && e.status === 422)
      throw new PushError('hub_unsupported', 'This hub cannot push to iPhones yet');
    throw e;
  }
  const rec: PushRecord = {
    hubUrl: o.hubUrl,
    id: reg.id,
    platform: t.platform,
    handle: h.endpoint ?? h.token ?? '',
    since: new Date(o.now ?? Date.now()).toISOString(),
  };
  await saveSecret(KEY, JSON.stringify(rec)).catch(() => undefined);
  return rec;
}

/** Turn push off: forget it on the box (best effort), with the distributor or OS, and here. */
export async function disablePush(api: OneMindApi, t: PushTransport | undefined, rec: PushRecord | undefined): Promise<void> {
  if (rec) await api.pushUnregister(rec.id).catch(() => undefined);
  await t?.release().catch(() => undefined);
  await deleteSecret(KEY);
}

/** The distributor moved this phone to a new endpoint: replace the registration on the box. */
export async function rotateEndpoint(api: OneMindApi, rec: PushRecord, e: UpEndpoint, label: string): Promise<PushRecord> {
  if (rec.platform !== 'unifiedpush' || e.url === rec.handle) return rec;
  await api.pushUnregister(rec.id).catch(() => undefined);
  const reg = await api.pushRegister({
    platform: 'unifiedpush',
    endpoint: e.url,
    ...(e.p256dh && e.auth ? { keys: { p256dh: e.p256dh, auth: e.auth } } : {}),
    label,
  });
  const next = { ...rec, id: reg.id, handle: e.url };
  await saveSecret(KEY, JSON.stringify(next)).catch(() => undefined);
  return next;
}

const ID = /^[A-Za-z0-9_-]{1,64}$/;

/**
 * A ping from the box, as delivered by APNs (notification data) or UnifiedPush (module event).
 * Only ids are accepted; anything that looks like content is ignored (D-005).
 */
export function parsePing(data: unknown): { id: string | undefined } | undefined {
  if (!data || typeof data !== 'object') return undefined;
  const d = data as Record<string, unknown>;
  if (!('notification_id' in d) && !('opaque_id' in d) && !('box_id' in d)) return undefined;
  const raw = d.notification_id ?? d.opaque_id;
  return { id: typeof raw === 'string' && ID.test(raw) ? raw : undefined };
}

export function blockerMessage(b: PushBlocker | 'failed', os: string = Platform.OS): string {
  switch (b) {
    case 'hub_unsupported':
      return 'This hub cannot send push yet (it comes with the notifications module). The app still alerts you while it is open.';
    case 'needs_device':
      return 'Push is set up per phone. Ask the owner to approve this phone first (This phone, above).';
    case 'no_distributor':
      return 'Install the ntfy app (F-Droid or Google Play) and add your box\'s ntfy server in it. OneMind then uses it to wake this phone; Google is not involved.';
    case 'no_permission':
      return 'Notifications are off for OneMind. Turn them on in the system settings.';
    case 'no_module':
      return os === 'android' ? 'This build has no push module (Expo Go or a test build).' : 'This build cannot receive push.';
    default:
      return 'Push could not be turned on.';
  }
}
