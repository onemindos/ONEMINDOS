// SPDX-License-Identifier: Apache-2.0
// Issue #704: lock-screen Review and Deny (never Approve), Deny only after unlock, and Lock OneMind.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as Notifications from 'expo-notifications';
import * as ScreenCapture from 'expo-screen-capture';
import * as SecureStore from 'expo-secure-store';
import type { ReactNode } from 'react';
import { AppState, Linking, Platform, Text, type AppStateStatus } from 'react-native';
import type { Action, InboxItem } from '../api/types';
import type { OneMindApi } from '../api/client';
import { HubDataProvider } from '../data';
import { APPROVAL_ACTIONS, setupNotifications, showAlert } from '../notify';
import { SessionProvider, useSession, type SessionDeps } from '../session';
import type { Connection } from '../storage';
import { v0Api } from '../test/fakes';
import { ACTION_DENY, ACTION_REVIEW, APPROVAL_CATEGORY, denyAfterUnlock, parseDenyLink, responseIntent, type ResponseLike } from './actions';
import { LOCK_KEY, LockProvider, RELOCK_MS } from './LockProvider';
import { LockSection } from './LockSection';
import { NotificationActions } from './NotificationActions';

// The Android native module, swapped per test (it is absent under Jest, as on iPhone).
const mockUp: { value: unknown } = { value: undefined };
jest.mock('../../modules/onemind-unifiedpush', () => ({
  get unifiedPush() {
    return mockUp.value;
  },
}));

// Jest runs in Node, but the app's tsconfig has no Node types: name only what this test uses.
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{ readFileSync(path: string, encoding: 'utf8'): string }>('fs');

const auth = LocalAuthentication.authenticateAsync as jest.Mock;
const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
const pendingAction = {
  type: 'app.remove', params: { app_id: 'ntfy' }, state: 'awaiting_approval',
  expires_at: new Date(Date.now() + 60 * 60_000).toISOString(),
} as Action;
const approvalNotice = (action_id: string): InboxItem => ({ topic: 'approvals', action_id }) as InboxItem;
const hubOffsetMs = () => 0;
const DEFAULT_TAP = 'expo.modules.notifications.actions.DEFAULT';

function response(actionIdentifier: string, data: Record<string, unknown> = { route: 'approvals', action_id: 'act-9' }, id = 'n1'): ResponseLike {
  return { actionIdentifier, notification: { request: { identifier: id, content: { data } } } };
}

let appStateListener: ((s: AppStateStatus) => void) | undefined;
let appStateSpy: jest.SpyInstance | undefined;
beforeEach(async () => {
  auth.mockReset();
  auth.mockResolvedValue({ success: true });
  (Notifications.addNotificationResponseReceivedListener as jest.Mock).mockClear();
  (SecureStore.setItemAsync as jest.Mock).mockClear();
  await SecureStore.deleteItemAsync(LOCK_KEY);
  appStateListener = undefined;
  appStateSpy = jest.spyOn(AppState, 'addEventListener').mockImplementation((_type, fn) => {
    appStateListener = fn as (s: AppStateStatus) => void;
    return { remove: jest.fn() } as unknown as ReturnType<typeof AppState.addEventListener>;
  });
});
afterEach(() => appStateSpy?.mockRestore());

describe('notification buttons', () => {
  it('offers exactly Review and Deny, both needing the phone unlocked, and never Approve', async () => {
    expect(APPROVAL_ACTIONS.map((a) => a.identifier)).toEqual([ACTION_REVIEW, ACTION_DENY]);
    for (const a of APPROVAL_ACTIONS) expect(a.options?.isAuthenticationRequired).toBe(true);
    expect(JSON.stringify(APPROVAL_ACTIONS)).not.toMatch(/approve/i);
    await setupNotifications();
    expect(Notifications.setNotificationCategoryAsync).toHaveBeenCalledWith(APPROVAL_CATEGORY, APPROVAL_ACTIONS);
  });

  it('puts the buttons only on a notification about a waiting request', async () => {
    const schedule = Notifications.scheduleNotificationAsync as jest.Mock;
    schedule.mockClear();
    await showAlert({ id: 'a1', title: 'Approval needed', body: 'agent x asks', route: 'approvals', actionId: 'act-9' });
    await showAlert({ id: 'a2', title: 'Node offline', body: 'n', route: 'nodes' });
    expect(schedule.mock.calls[0][0].content).toEqual(expect.objectContaining({ categoryIdentifier: APPROVAL_CATEGORY, data: { route: 'approvals', action_id: 'act-9' } }));
    expect(schedule.mock.calls[1][0].content.categoryIdentifier).toBeUndefined();
  });

  it('a tap or Review only opens the app; Deny is the only thing a button decides', () => {
    expect(responseIntent(response(DEFAULT_TAP))).toEqual({ kind: 'open', data: { route: 'approvals', action_id: 'act-9' } });
    expect(responseIntent(response(ACTION_REVIEW))).toEqual({ kind: 'open', data: { route: 'approvals', action_id: 'act-9' } });
    expect(responseIntent(response(ACTION_DENY))).toEqual({ kind: 'deny', target: { actionId: 'act-9' } });
    expect(responseIntent(response('approve'))).toEqual({ kind: 'open', data: { route: 'approvals', action_id: 'act-9' } });
    expect(responseIntent(response(ACTION_DENY, { route: 'approvals', action_id: '../x' }))).toEqual(expect.objectContaining({ kind: 'open' }));
  });

  it('reads the closed-app Deny links and nothing else', () => {
    expect(parseDenyLink('onemind://approvals?deny=act-9')).toEqual({ actionId: 'act-9' });
    expect(parseDenyLink('onemind://approvals?deny_notification=ntf_1')).toEqual({ notificationId: 'ntf_1' });
    expect(parseDenyLink('onemind://approvals?review=act-9')).toBeUndefined();
    expect(parseDenyLink('onemind://approvals?approve=act-9')).toBeUndefined();
    expect(parseDenyLink('https://evil.example/approvals?deny=act-9')).toBeUndefined();
  });

  it('the closed-app Android notification marks both buttons authentication-required and has no Approve', () => {
    const dir = `${__dirname}/../../modules/onemind-unifiedpush/android/src/main/java/os/onemind/unifiedpush`;
    const kt = readFileSync(`${dir}/Notices.kt`, 'utf8');
    expect(kt).toMatch(/setAuthenticationRequired\(true\)/);
    expect(kt.match(/addAction\(lockedAction\(context, "(Review|Deny)"/g)).toHaveLength(4);
    expect(kt).toContain('lockedAction(context, "Review", "onemind://approvals?review_notification=$id")');
    expect(kt).not.toMatch(/"Approve"|approve=/);
    expect(readFileSync(`${dir}/OneMindPushService.kt`, 'utf8')).toMatch(/Notices\.showOpaque/);
  });

  it('guards both Android action pairs at Android 12 and leaves the ordinary tap on older versions', () => {
    const kt = readFileSync(`${__dirname}/../../modules/onemind-unifiedpush/android/src/main/java/os/onemind/unifiedpush/Notices.kt`, 'utf8');
    const guardedActions = kt.matchAll(/if \(Build\.VERSION\.SDK_INT >= Build\.VERSION_CODES\.S(?: && id != null)?\) \{([^}]+)\}/g);
    expect([...guardedActions].map(([, body]) => body?.match(/addAction\(lockedAction/g)?.length)).toEqual([2, 2]);
    expect(kt).toContain('.setContentIntent(link(context, open))');
    expect(kt).toContain('.setContentIntent(link(context, review))');
  });

  // Jest mocks expo-local-authentication, so only the config can catch this: if app.json blocks
  // USE_BIOMETRIC, the manifest merger strips it, BiometricPrompt fails on Android, the Lock OneMind
  // switch stays off and every lock-screen Deny ends as cancelled.
  it('app.json loads expo-local-authentication and does not block the biometric permissions it needs', () => {
    const { expo } = JSON.parse(readFileSync(`${__dirname}/../../app.json`, 'utf8')) as {
      expo: { plugins: (string | [string, unknown])[]; android: { blockedPermissions?: string[] } };
    };
    expect(expo.plugins.some((p) => (Array.isArray(p) ? p[0] : p) === 'expo-local-authentication')).toBe(true);
    const blocked = expo.android.blockedPermissions ?? [];
    expect(blocked).not.toContain('android.permission.USE_BIOMETRIC');
    expect(blocked).not.toContain('android.permission.USE_FINGERPRINT');
  });
});

describe('Deny after unlock', () => {
  it('records nothing when the unlock is cancelled, and a deny once it succeeds', async () => {
    const deny = jest.fn(async () => ({}) as never);
    const action = jest.fn(async () => pendingAction);
    const api = { deny, notification: jest.fn(), action, hubOffsetMs };
    expect((await denyAfterUnlock(api, { actionId: 'act-9' }, async () => false)).outcome).toBe('cancelled');
    expect(deny).not.toHaveBeenCalled();
    const confirm = jest.fn(async () => true);
    expect((await denyAfterUnlock(api, { actionId: 'act-9' }, confirm)).outcome).toBe('denied');
    expect(confirm).toHaveBeenCalledWith('Unlock to deny: Remove ntfy', 'act-9');
    expect(deny).toHaveBeenCalledWith('act-9');
  });

  it('finds the request behind a closed-app ping, and asks nothing when there is none', async () => {
    const deny = jest.fn(async () => ({}) as never);
    const confirm = jest.fn(async () => true);
    const action = jest.fn(async () => pendingAction);
    const withAction = { deny, action, hubOffsetMs, notification: jest.fn(async () => approvalNotice('act-3')) };
    expect((await denyAfterUnlock(withAction, { notificationId: 'ntf_1' }, confirm)).outcome).toBe('denied');
    expect(deny).toHaveBeenCalledWith('act-3');
    deny.mockClear();
    confirm.mockClear();
    const plain = { deny, action, hubOffsetMs, notification: jest.fn(async () => ({ action_id: null }) as never) };
    expect((await denyAfterUnlock(plain, { notificationId: 'ntf_2' }, confirm)).outcome).toBe('nothing_to_deny');
    expect(confirm).not.toHaveBeenCalled();
    expect(deny).not.toHaveBeenCalled();
  });
  it.each(['succeeded', 'failed', 'expired', 'cancelled', 'expired by time'])(
    'skips authentication for a stale %s request', async (state) => {
      const a = state === 'expired by time'
        ? { ...pendingAction, expires_at: new Date(0).toISOString() }
        : { ...pendingAction, state: state as Action['state'] };
      const api = v0Api({ action: async () => a, deny: jest.fn() });
      const confirm = jest.fn(async () => true);
      expect((await denyAfterUnlock(api, { actionId: 'act-stale' }, confirm)).outcome).toBe('nothing_to_deny');
      expect(confirm).not.toHaveBeenCalled();
      expect(api.deny).not.toHaveBeenCalled();
    },
  );

  it('ignores an opaque ping for a completed action that carries an action ID', async () => {
    const api = v0Api({
      notification: async () => ({ ...approvalNotice('act-other'), topic: 'apps' }),
      action: jest.fn(),
      deny: jest.fn(),
    });
    const confirm = jest.fn(async () => true);
    expect((await denyAfterUnlock(api, { notificationId: 'ntf-completed' }, confirm)).outcome).toBe('nothing_to_deny');
    expect(api.action).not.toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
    expect(api.deny).not.toHaveBeenCalled();
  });

});

function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

async function mountActions(over: Partial<OneMindApi>, open = jest.fn()) {
  const api = v0Api({ action: async () => pendingAction, ...over });
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  // The key mirrors App's <SignedIn key={hubUrl}>: changing it mounts NotificationActions again.
  const tree = (key: number) => (
    <SessionProvider deps={deps}>
      <Gate>
        <LockProvider key={key}>
          <HubDataProvider intervalMs={0}>
            <NotificationActions open={open} />
            <Text>home</Text>
          </HubDataProvider>
        </LockProvider>
      </Gate>
    </SessionProvider>
  );
  const view = await render(tree(0));
  await screen.findByText('home');
  await waitFor(() => expect(Notifications.addNotificationResponseReceivedListener).toHaveBeenCalled());
  const listener = (Notifications.addNotificationResponseReceivedListener as jest.Mock).mock.calls.at(-1)[0] as (r: ResponseLike) => void;
  let n = 0;
  const remount = async () => {
    await view.rerender(tree(++n));
    await screen.findByText('home');
    await act(async () => undefined);
  };
  return { listener, open, remount };
}

describe('NotificationActions', () => {
  it('Deny from the lock screen asks for an unlock first and records the deny only after it', async () => {
    const order: string[] = [];
    const deny = jest.fn(async () => {
      order.push('deny');
      return {} as never;
    });
    const approve = jest.fn();
    const { listener } = await mountActions({ deny, approve });
    auth.mockImplementationOnce(async () => {
      order.push('unlock-cancelled');
      return { success: false, error: 'user_cancel' };
    });
    await act(async () => listener(response(ACTION_DENY, undefined, 'n1')));
    await waitFor(() => expect(order).toEqual(['unlock-cancelled']));
    expect(deny).not.toHaveBeenCalled();

    auth.mockImplementationOnce(async () => {
      order.push('unlocked');
      return { success: true };
    });
    await act(async () => listener(response(ACTION_DENY, undefined, 'n2')));
    await waitFor(() => expect(deny).toHaveBeenCalledWith('act-9'));
    expect(order).toEqual(['unlock-cancelled', 'unlocked', 'deny']);
    expect(approve).not.toHaveBeenCalled();
  });

  it('requires separate confirmation for simultaneous requests with the same title', async () => {
    const deny = jest.fn(async () => pendingAction);
    const { listener } = await mountActions({ deny });
    let finishFirst!: (result: { success: boolean }) => void;
    auth.mockImplementationOnce(() => new Promise((resolve) => { finishFirst = resolve; }));
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });

    await act(async () => {
      listener(response(ACTION_DENY, { action_id: 'act-same-title-1' }, 'ntf-same-title-1'));
      listener(response(ACTION_DENY, { action_id: 'act-same-title-2' }, 'ntf-same-title-2'));
    });
    expect(auth).toHaveBeenCalledTimes(1);
    expect(deny).not.toHaveBeenCalled();
    await act(async () => finishFirst({ success: true }));
    expect(auth).toHaveBeenCalledTimes(2);
    expect(auth.mock.calls.map(([options]) => options.promptMessage)).toEqual([
      'Unlock to deny: Remove ntfy\nRequest act-same-title-1',
      'Unlock to deny: Remove ntfy\nRequest act-same-title-2',
    ]);
    expect(deny.mock.calls).toEqual([['act-same-title-1']]);
  });

  it('puts the Android request ID in the description so the native title can show the action', async () => {
    const original = Platform.OS;
    Platform.OS = 'android';
    try {
      const deny = jest.fn(async () => pendingAction);
      const { listener } = await mountActions({ deny });
      await act(async () => listener(response(ACTION_DENY, { action_id: 'act-android-title' }, 'ntf-android-title')));
      expect(auth).toHaveBeenCalledWith(expect.objectContaining({
        promptMessage: 'Unlock to deny: Remove ntfy',
        promptDescription: 'Request act-android-title',
      }));
      expect(deny).toHaveBeenCalledWith('act-android-title');
    } finally {
      Platform.OS = original;
    }
  });

  it('coalesces direct and opaque deliveries for one request into one prompt and one Deny', async () => {
    const api = v0Api({
      action: async () => pendingAction,
      notification: async () => approvalNotice('act-duplicate'),
      deny: jest.fn(async () => pendingAction),
    });
    let finish!: (result: boolean) => void;
    const confirmed = new Promise<boolean>((resolve) => { finish = resolve; });
    const confirm = jest.fn(() => confirmed);
    const direct = denyAfterUnlock(api, { actionId: 'act-duplicate' }, confirm);
    const opaque = denyAfterUnlock(api, { notificationId: 'ntf-duplicate' }, confirm);
    await waitFor(() => expect(confirm).toHaveBeenCalledTimes(1));
    finish(true);
    expect((await Promise.all([direct, opaque])).map((r) => r.outcome)).toEqual(['denied', 'denied']);
    expect(api.deny).toHaveBeenCalledTimes(1);
    expect(api.deny).toHaveBeenCalledWith('act-duplicate');
  });

  it('consumes a cancelled warm response across remounts and accepts a fresh tap', async () => {
    let cached: ResponseLike | null = null;
    const read = jest.mocked(Notifications.getLastNotificationResponseAsync);
    const clear = jest.mocked(Notifications.clearLastNotificationResponse);
    read.mockImplementation(async () => cached as Awaited<ReturnType<typeof Notifications.getLastNotificationResponseAsync>>);
    clear.mockImplementation(() => { cached = null; });
    try {
      const deny = jest.fn(async () => pendingAction);
      const { listener, remount } = await mountActions({ deny });
      const tap = response(ACTION_DENY, { action_id: 'act-warm' }, 'ntf-warm-cancel');
      auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
      await act(async () => { cached = tap; listener(tap); });
      expect(cached).toBeNull();
      expect(auth).toHaveBeenCalledTimes(1);
      expect(deny).not.toHaveBeenCalled();

      await remount();
      expect(auth).toHaveBeenCalledTimes(1);
      const freshListener = jest.mocked(Notifications.addNotificationResponseReceivedListener).mock.calls.at(-1)![0];
      await act(async () => {
        cached = tap;
        freshListener(tap as Parameters<typeof freshListener>[0]);
      });
      expect(auth).toHaveBeenCalledTimes(2);
      expect(deny).toHaveBeenCalledWith('act-warm');
    } finally {
      read.mockResolvedValue(null);
      clear.mockImplementation(() => undefined);
    }
  });

  it.each(['lookup', 'decision'] as const)('retries a transient %s failure only on a fresh Deny tap', async (failure) => {
    const action = jest.fn(async () => pendingAction);
    const deny = jest.fn(async () => pendingAction);
    const failingCall = failure === 'lookup' ? action : deny;
    failingCall.mockRejectedValueOnce(new Error('Hub unavailable'));
    const tap = response(ACTION_DENY, { action_id: 'act-offline' }, `ntf-offline-${failure}`);
    const read = jest.mocked(Notifications.getLastNotificationResponseAsync);
    read.mockResolvedValue(tap as Awaited<ReturnType<typeof Notifications.getLastNotificationResponseAsync>>);
    try {
      const { remount } = await mountActions({ action, deny });
      await waitFor(() => expect(failingCall).toHaveBeenCalledTimes(1));
      await remount();
      expect(action).toHaveBeenCalledTimes(1);

      const listener = jest.mocked(Notifications.addNotificationResponseReceivedListener).mock.calls.at(-1)![0];
      await act(async () => listener(tap as Parameters<typeof listener>[0]));
      expect(action).toHaveBeenCalledTimes(2);
      expect(deny).toHaveBeenCalledTimes(failure === 'lookup' ? 1 : 2);
      expect(deny).toHaveBeenLastCalledWith('act-offline');
    } finally {
      read.mockResolvedValue(null);
    }
  });

  it('a tap or Review never approves or denies; it only opens the approval card', async () => {
    const deny = jest.fn();
    const approve = jest.fn();
    const { listener, open } = await mountActions({ deny, approve });
    await act(async () => listener(response(DEFAULT_TAP, undefined, 'n3')));
    await act(async () => listener(response(ACTION_REVIEW, undefined, 'n4')));
    expect(open).toHaveBeenCalledTimes(2);
    expect(open).toHaveBeenLastCalledWith(expect.objectContaining({ route: 'approvals' }));
    expect(approve).not.toHaveBeenCalled();
    expect(deny).not.toHaveBeenCalled();
    expect(auth).not.toHaveBeenCalled();
  });
});

describe('Lock OneMind', () => {
  async function mountLock(now: () => number = Date.now) {
    await render(
      <LockProvider now={now}>
        <Text>home</Text>
        <LockSection />
      </LockProvider>,
    );
    await screen.findByTestId('lock-section', { includeHiddenElements: true });
    await waitFor(() => expect(screen.queryByTestId('app-lock-checking')).toBeNull());
  }

  it('turning the lock on needs an unlock, and a cancelled unlock leaves it off', async () => {
    await mountLock();
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await fireEvent.press(screen.getByTestId('lock-toggle'));
    expect(await screen.findByText(/Not changed/)).toBeTruthy();
    expect(await SecureStore.getItemAsync(LOCK_KEY)).toBeNull();
    await fireEvent.press(screen.getByTestId('lock-toggle'));
    await waitFor(async () => expect(await SecureStore.getItemAsync(LOCK_KEY)).toBe('on'));
    expect(screen.getByText('Turn lock off')).toBeTruthy();
    expect(auth).toHaveBeenCalledTimes(2);
    // The lock never moves a token behind requireAuthentication: background photo backup keeps working.
    for (const call of (SecureStore.setItemAsync as jest.Mock).mock.calls) expect(call[2]?.requireAuthentication).toBeFalsy();
  });

  it('keeps an enabled lock covered when enrollment cannot be read and unlocks after a successful retry', async () => {
    await SecureStore.setItemAsync(LOCK_KEY, 'on');
    jest.mocked(LocalAuthentication.getEnrolledLevelAsync).mockRejectedValueOnce(new Error('Unavailable'));
    await mountLock();
    expect(screen.getByTestId('app-lock')).toBeTruthy();
    expect(screen.queryByText('home')).toBeNull();
    expect(auth).not.toHaveBeenCalled();
    expect(await SecureStore.getItemAsync(LOCK_KEY)).toBe('on');

    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await fireEvent.press(screen.getByText('Retry'));
    expect(await screen.findByTestId('unlock')).toBeTruthy();
    expect(screen.queryByText('home')).toBeNull();
    await fireEvent.press(screen.getByTestId('unlock'));
    expect(await screen.findByText('home')).toBeTruthy();
    expect(auth).toHaveBeenCalledTimes(2);
  });

  it('keeps a failed preference read covered, then honors the stored preference on retry', async () => {
    await SecureStore.setItemAsync(LOCK_KEY, 'on');
    jest.mocked(SecureStore.getItemAsync).mockRejectedValueOnce(new Error('Keychain unavailable'));
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await render(<LockProvider><Text>home</Text></LockProvider>);
    const retry = await screen.findByText('Retry');
    expect(screen.queryByText('home')).toBeNull();
    expect(auth).not.toHaveBeenCalled();

    await fireEvent.press(retry);
    expect(await screen.findByTestId('unlock')).toBeTruthy();
    expect(screen.queryByText('home')).toBeNull();
    await fireEvent.press(screen.getByTestId('unlock'));
    expect(await screen.findByText('home')).toBeTruthy();
    expect(auth).toHaveBeenCalledTimes(2);
  });

  it('with the lock on, opening the app shows the prompt, and coming back after a while prompts again', async () => {
    await SecureStore.setItemAsync(LOCK_KEY, 'on');
    let t = 1_000_000;
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await mountLock(() => t);
    expect(await screen.findByTestId('app-lock')).toBeTruthy();
    expect(auth).toHaveBeenCalledTimes(1);
    await fireEvent.press(screen.getByTestId('unlock'));
    await waitFor(() => expect(screen.queryByTestId('app-lock')).toBeNull());

    // A short trip to the background keeps it unlocked.
    await act(async () => appStateListener?.('background'));
    t += RELOCK_MS - 1;
    await act(async () => appStateListener?.('active'));
    expect(screen.queryByTestId('app-lock')).toBeNull();
    expect(auth).toHaveBeenCalledTimes(2);

    // Longer than RELOCK_MS: locked again, and the prompt appears on resume.
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await act(async () => appStateListener?.('background'));
    t += RELOCK_MS;
    await act(async () => appStateListener?.('active'));
    expect(await screen.findByTestId('app-lock')).toBeTruthy();
    expect(auth).toHaveBeenCalledTimes(3);
  });

  it.each(['ios', 'android'] as const)('protects the %s snapshot natively while enabled', async (os) => {
    const original = Platform.OS;
    Platform.OS = os;
    const protect = os === 'ios' ? ScreenCapture.enableAppSwitcherProtectionAsync : ScreenCapture.preventScreenCaptureAsync;
    const restore = os === 'ios' ? ScreenCapture.disableAppSwitcherProtectionAsync : ScreenCapture.allowScreenCaptureAsync;
    jest.mocked(protect).mockClear();
    jest.mocked(restore).mockClear();
    try {
      await mountLock();
      expect(protect).not.toHaveBeenCalled();
      await fireEvent.press(screen.getByTestId('lock-toggle'));
      await waitFor(() => expect(protect).toHaveBeenCalledWith(os === 'ios' ? 1 : LOCK_KEY));

      await act(async () => appStateListener?.('inactive'));
      expect(screen.queryByText('home')).toBeNull();
      await act(async () => appStateListener?.('active'));
      expect(screen.getByText('home')).toBeTruthy();
      await fireEvent.press(screen.getByTestId('lock-toggle'));
      await waitFor(() => expect(restore).toHaveBeenCalledTimes(1));
      expect(auth).toHaveBeenCalledTimes(2);
    } finally {
      Platform.OS = original;
    }
  });

  it('hides the app from screen readers while locked, and shows it again after the unlock', async () => {
    await SecureStore.setItemAsync(LOCK_KEY, 'on');
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await render(
      <LockProvider>
        <Text>home</Text>
      </LockProvider>,
    );
    const content = await screen.findByTestId('app-content', { includeHiddenElements: true });
    expect(content.props.importantForAccessibility).toBe('no-hide-descendants');
    expect(content.props.accessibilityElementsHidden).toBe(true);
    expect((await screen.findByTestId('app-lock')).props.accessibilityViewIsModal).toBe(true);
    await fireEvent.press(screen.getByTestId('unlock'));
    await waitFor(() => expect(screen.queryByTestId('app-lock')).toBeNull());
    const open = screen.getByTestId('app-content');
    expect(open.props.importantForAccessibility).toBe('auto');
    expect(open.props.accessibilityElementsHidden).toBe(false);
  });
});

describe('Deny prompt', () => {
  it('names the request, and does not borrow the answer to another prompt', async () => {
    const { authenticate } = jest.requireActual<typeof import('./auth')>('./auth');
    const asked: string[] = [];
    let release: (v: { success: boolean }) => void = () => undefined;
    auth.mockImplementationOnce((o: { promptMessage: string }) => {
      asked.push(o.promptMessage);
      return new Promise((res) => (release = res));
    });
    auth.mockImplementation(async (o: { promptMessage: string }) => {
      asked.push(o.promptMessage);
      return { success: true };
    });
    const unlock = authenticate('Unlock OneMind');
    const sameAgain = authenticate('Unlock OneMind');
    const denyPrompt = authenticate('Unlock to deny: Remove ntfy');
    await Promise.resolve();
    expect(asked).toEqual(['Unlock OneMind']);
    release({ success: true });
    expect(await Promise.all([unlock, sameAgain, denyPrompt])).toEqual([true, true, true]);
    expect(asked).toEqual(['Unlock OneMind', 'Unlock to deny: Remove ntfy']);
  });

  it('a Deny whose request cannot be found asks nothing and denies nothing', async () => {
    const deny = jest.fn();
    const confirm = jest.fn(async () => true);
    const api = { deny, notification: jest.fn(), hubOffsetMs, action: jest.fn(async () => Promise.reject(new Error('404'))) };
    expect((await denyAfterUnlock(api, { actionId: 'act-1' }, confirm)).outcome).toBe('failed');
    expect(confirm).not.toHaveBeenCalled();
    expect(deny).not.toHaveBeenCalled();
  });
});

describe('Android approval notification', () => {
  const realOS = Platform.OS;
  const schedule = Notifications.scheduleNotificationAsync as jest.Mock;
  const approval = { id: 'a1', title: 'Approval needed', body: 'agent x asks', route: 'approvals' as const, actionId: 'act-9' };
  beforeEach(() => schedule.mockClear());
  afterEach(() => {
    Platform.OS = realOS;
    mockUp.value = undefined;
  });

  it('hands an approval to the native module with its action id, not to expo-notifications', async () => {
    Platform.OS = 'android';
    const showApproval = jest.fn();
    mockUp.value = { showApproval };
    await showAlert(approval);
    expect(showApproval).toHaveBeenCalledWith('a1', 'Approval needed', 'agent x asks', 'act-9');
    expect(schedule).not.toHaveBeenCalled();
  });

  it('keeps other alerts on expo-notifications', async () => {
    Platform.OS = 'android';
    const showApproval = jest.fn();
    mockUp.value = { showApproval };
    await showAlert({ id: 'a2', title: 'Node offline', body: 'n', route: 'nodes' });
    expect(showApproval).not.toHaveBeenCalled();
    expect(schedule).toHaveBeenCalledTimes(1);
  });

  it('falls back to expo-notifications when the native build has no showApproval', async () => {
    Platform.OS = 'android';
    mockUp.value = {};
    await showAlert(approval);
    expect(schedule).toHaveBeenCalledTimes(1);
    const { content } = schedule.mock.calls[0][0];
    expect(content).toEqual(expect.objectContaining({ data: { route: 'approvals', action_id: 'act-9' } }));
    expect(content).not.toHaveProperty('categoryIdentifier');
    expect(responseIntent(response(DEFAULT_TAP, content.data))).toEqual({ kind: 'open', data: content.data });
  });
});

describe('Android Deny links reach the deny', () => {
  let urlListener: ((e: { url: string }) => void) | undefined;
  let initialUrl: string | null = null;
  let linkSpies: jest.SpyInstance[] = [];
  beforeEach(() => {
    urlListener = undefined;
    initialUrl = null;
    linkSpies = [];
    linkSpies.push(jest.spyOn(Linking, 'addEventListener').mockImplementation(((_t: string, fn: (e: { url: string }) => void) => {
      urlListener = fn;
      return { remove: jest.fn() };
    }) as never));
    linkSpies.push(jest.spyOn(Linking, 'getInitialURL').mockImplementation(async () => initialUrl));
    (Notifications.getLastNotificationResponseAsync as jest.Mock).mockResolvedValue(null);
  });
  afterEach(() => {
    linkSpies.forEach((x) => x.mockRestore());
    (Notifications.getLastNotificationResponseAsync as jest.Mock).mockResolvedValue(null);
  });
  const act9 = async () => pendingAction;

  it('a ?deny= link while the app runs unlocks first, then denies that action', async () => {
    const order: string[] = [];
    const deny = jest.fn(async () => (order.push('deny'), {} as never));
    await mountActions({ deny, action: act9 });
    auth.mockImplementationOnce(async () => (order.push('unlock'), { success: true }));
    await act(async () => urlListener?.({ url: 'onemind://approvals?deny=act-link1' }));
    await waitFor(() => expect(deny).toHaveBeenCalledWith('act-link1'));
    expect(order).toEqual(['unlock', 'deny']);
  });

  it('a ?deny_notification= link finds the action behind the ping, unlocks, then denies', async () => {
    const order: string[] = [];
    const deny = jest.fn(async () => (order.push('deny'), {} as never));
    const notification = jest.fn(async () => approvalNotice('act-ntf'));
    await mountActions({ deny, notification, action: act9 });
    auth.mockImplementationOnce(async () => (order.push('unlock'), { success: true }));
    await act(async () => urlListener?.({ url: 'onemind://approvals?deny_notification=ntf_7' }));
    await waitFor(() => expect(deny).toHaveBeenCalledWith('act-ntf'));
    expect(notification).toHaveBeenCalledWith('ntf_7');
    expect(order).toEqual(['unlock', 'deny']);
  });

  it('denies nothing when the unlock is cancelled, and ignores links that are not Deny links', async () => {
    const deny = jest.fn();
    await mountActions({ deny, action: act9 });
    auth.mockResolvedValueOnce({ success: false, error: 'user_cancel' });
    await act(async () => urlListener?.({ url: 'onemind://approvals?deny=act-cancel' }));
    await waitFor(() => expect(auth).toHaveBeenCalledTimes(1));
    await act(async () => urlListener?.({ url: 'onemind://approvals?approve=act-x' }));
    await act(async () => urlListener?.({ url: 'https://evil.example/?deny=act-x' }));
    expect(deny).not.toHaveBeenCalled();
    expect(auth).toHaveBeenCalledTimes(1);
  });

  it('ignores malformed Deny links without throwing or prompting', async () => {
    const deny = jest.fn();
    const action = jest.fn(async () => pendingAction);
    await mountActions({ deny, action });
    await act(async () => {
      // A valid ID elsewhere in the query must never let a malformed link through.
      urlListener?.({ url: 'onemind://approvals?deny=act-valid&other=%E0%A4%A' });
      urlListener?.({ url: 'onemind://approvals?deny_notification=%ZZ' });
    });
    expect(action).not.toHaveBeenCalled();
    expect(auth).not.toHaveBeenCalled();
    expect(deny).not.toHaveBeenCalled();
  });

  it('a launch URL from a closed-app Deny button denies after unlock, and a second mount does not replay it', async () => {
    initialUrl = 'onemind://approvals?deny=act-cold';
    const deny = jest.fn(async () => ({}) as never);
    const { remount, open } = await mountActions({ deny, action: act9 });
    await waitFor(() => expect(deny).toHaveBeenCalledWith('act-cold'));
    expect(auth).toHaveBeenCalledTimes(1);
    await remount();
    expect(deny).toHaveBeenCalledTimes(1);
    expect(auth).toHaveBeenCalledTimes(1);
    expect(open).not.toHaveBeenCalled();
  });

  it('a last notification response is handled once across mounts, and cleared', async () => {
    (Notifications.getLastNotificationResponseAsync as jest.Mock).mockResolvedValue(response(ACTION_DENY, { route: 'approvals', action_id: 'act-last' }, 'n-last'));
    const deny = jest.fn(async () => ({}) as never);
    const { remount, open } = await mountActions({ deny, action: act9 });
    await waitFor(() => expect(deny).toHaveBeenCalledWith('act-last'));
    expect(Notifications.clearLastNotificationResponse).toHaveBeenCalled();
    await remount();
    expect(deny).toHaveBeenCalledTimes(1);
  });
});
