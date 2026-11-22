// SPDX-License-Identifier: Apache-2.0
// Issue #704: lock-screen Review and Deny (never Approve), Deny only after unlock, and Lock OneMind.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as LocalAuthentication from 'expo-local-authentication';
import * as Notifications from 'expo-notifications';
import * as SecureStore from 'expo-secure-store';
import type { ReactNode } from 'react';
import { AppState, Text, type AppStateStatus } from 'react-native';
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

// Jest runs in Node, but the app's tsconfig has no Node types: name only what this test uses.
declare const __dirname: string;
const { readFileSync } = jest.requireActual<{ readFileSync(path: string, encoding: 'utf8'): string }>('fs');

const auth = LocalAuthentication.authenticateAsync as jest.Mock;
const LIVE: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 't' };
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
    expect(kt).not.toMatch(/"Approve"|approve=/);
    expect(readFileSync(`${dir}/OneMindPushService.kt`, 'utf8')).toMatch(/Notices\.showOpaque/);
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
    const api = { deny, notification: jest.fn() };
    expect((await denyAfterUnlock(api, { actionId: 'act-9' }, async () => false)).outcome).toBe('cancelled');
    expect(deny).not.toHaveBeenCalled();
    expect((await denyAfterUnlock(api, { actionId: 'act-9' }, async () => true)).outcome).toBe('denied');
    expect(deny).toHaveBeenCalledWith('act-9');
  });

  it('finds the request behind a closed-app ping, and asks nothing when there is none', async () => {
    const deny = jest.fn(async () => ({}) as never);
    const confirm = jest.fn(async () => true);
    const withAction = { deny, notification: jest.fn(async () => ({ action_id: 'act-3' }) as never) };
    expect((await denyAfterUnlock(withAction, { notificationId: 'ntf_1' }, confirm)).outcome).toBe('denied');
    expect(deny).toHaveBeenCalledWith('act-3');
    deny.mockClear();
    confirm.mockClear();
    const plain = { deny, notification: jest.fn(async () => ({ action_id: null }) as never) };
    expect((await denyAfterUnlock(plain, { notificationId: 'ntf_2' }, confirm)).outcome).toBe('nothing_to_deny');
    expect(confirm).not.toHaveBeenCalled();
    expect(deny).not.toHaveBeenCalled();
  });
});

function Gate({ children }: { children: ReactNode }) {
  return useSession().session ? children : null;
}

async function mountActions(over: Partial<OneMindApi>, open = jest.fn()) {
  const api = v0Api(over);
  const deps: SessionDeps = { load: async () => LIVE, save: async () => undefined, clear: async () => undefined, makeApi: () => api };
  await render(
    <SessionProvider deps={deps}>
      <Gate>
        <LockProvider>
          <HubDataProvider intervalMs={0}>
            <NotificationActions open={open} />
            <Text>home</Text>
          </HubDataProvider>
        </LockProvider>
      </Gate>
    </SessionProvider>,
  );
  await screen.findByText('home');
  await waitFor(() => expect(Notifications.addNotificationResponseReceivedListener).toHaveBeenCalled());
  const listener = (Notifications.addNotificationResponseReceivedListener as jest.Mock).mock.calls.at(-1)[0] as (r: ResponseLike) => void;
  return { listener, open };
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
    await screen.findByTestId('lock-section');
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
});
