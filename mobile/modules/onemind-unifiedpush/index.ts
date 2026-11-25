// SPDX-License-Identifier: Apache-2.0
// JS side of the UnifiedPush module (Android only). On iPhone, in tests and in Expo Go the native
// module is absent and `unifiedPush` is undefined; callers treat that as "not available here".
import { requireOptionalNativeModule, type EventSubscription } from 'expo';

export interface UpEndpoint {
  url: string;
  p256dh: string | null;
  auth: string | null;
  temporary: boolean;
}

type Events = {
  onNewEndpoint: (e: UpEndpoint) => void;
  onMessage: (e: { id: string | null }) => void;
  onRegistrationFailed: (e: { reason: 'INTERNAL_ERROR' | 'NETWORK' | 'ACTION_REQUIRED' | 'VAPID_REQUIRED' }) => void;
  onUnregistered: (e: Record<string, never>) => void;
};

export interface UnifiedPushNative {
  distributors(): string[];
  savedDistributor(): string | null;
  saveDistributor(pkg: string): void;
  useDefaultDistributor(): Promise<boolean>;
  register(vapid: string | null): void;
  unregister(): void;
  lastEndpoint(): UpEndpoint | null;
  /**
   * Show an approval notification with Review and Deny buttons that need the phone unlocked
   * (setAuthenticationRequired, Android 12+). Never an Approve button. Optional: older builds lack it.
   */
  showApproval?(tag: string, title: string, body: string, actionId: string): void;
  /** When the last ping arrived (ms since epoch), also while the app was closed. Absent in builds before it. */
  lastPingAt?(): number | null;
  addListener<K extends keyof Events>(event: K, listener: Events[K]): EventSubscription;
}

export const unifiedPush: UnifiedPushNative | undefined = requireOptionalNativeModule<UnifiedPushNative>('OneMindUnifiedPush') ?? undefined;
