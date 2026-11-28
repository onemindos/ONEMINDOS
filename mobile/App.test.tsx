// SPDX-License-Identifier: Apache-2.0
// Smoke test of the whole shell: Connect → sign in with a token → tabs → Me → Inbox. The gateway is the
// in-memory fake (src/test/mockHub.ts) handed in for the test; the app itself has no demo to open.
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as Notifications from 'expo-notifications';
import { Linking } from 'react-native';
import App, { AppRoot } from './App';
import { makeActions, makeInbox } from './src/api/fixtures';
import type { Connection } from './src/storage';
import { mockApi } from './src/test/mockHub';

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);
// Signed in as a person to a hub, the app also watches for files shared into it: nothing is shared here.
jest.mock('expo-sharing', () => ({ getSharedPayloads: () => [], getResolvedSharedPayloadsAsync: async () => [], clearSharedPayloads: jest.fn() }));

const deps = (save = jest.fn(async (_c: Connection) => undefined)) => ({ load: async () => null, save, clear: async () => undefined, makeApi: mockApi });

describe('app shell', () => {
  afterEach(() => jest.restoreAllMocks());

  it('starts at Connect with passkey sign-in first, signs in with a token, and reaches the Inbox through Me', async () => {
    await render(<AppRoot deps={deps()} />);
    expect(await screen.findByTestId('brand-mark')).toBeTruthy();
    expect(screen.getByTestId('passkey-sign-in')).toBeTruthy();
    expect(screen.queryByTestId('token')).toBeNull();
    await fireEvent.changeText(screen.getByTestId('hub-url'), 'https://hub.example');
    await fireEvent.press(screen.getByTestId('use-token'));
    await fireEvent.changeText(screen.getByTestId('token'), 'owner-demo');
    await fireEvent.press(screen.getByTestId('connect'));
    expect(await screen.findByText('Home OneMind')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('review-first'));
    expect(await screen.findByTestId('pending-act-0001')).toBeTruthy();
    await fireEvent.press(screen.getByTestId('tab-me'));
    for (const id of ['Settings', 'Activity', 'Inbox', 'Nodes', 'Tips', 'DeviceInfo', 'PhotoBackup']) {
      expect(await screen.findByTestId(`more-${id}`)).toBeTruthy();
    }
    await fireEvent.press(await screen.findByTestId('more-Inbox'));
    expect(await screen.findByTestId('ntf-ntf_demo_01')).toBeTruthy();
  });

  it('Connect offers no demo: only your own hub', async () => {
    await render(<App />);
    expect(await screen.findByTestId('passkey-sign-in')).toBeTruthy();
    expect(screen.queryByText(/demo/i)).toBeNull();
    expect(screen.queryByTestId('demo-owner-demo')).toBeNull();
    expect(screen.queryByTestId('demo-adult-demo')).toBeNull();
    expect(screen.queryByTestId('demo-agent-demo')).toBeNull();
  });

  it('the onemind://demo link connects nothing, at start or while open', async () => {
    const listeners: ((e: { url: string }) => void)[] = [];
    jest.spyOn(Linking, 'getInitialURL').mockResolvedValue('onemind://demo?as=owner');
    jest.spyOn(Linking, 'addEventListener').mockImplementation((_type, fn) => {
      listeners.push(fn as (e: { url: string }) => void);
      return { remove: jest.fn() } as unknown as ReturnType<typeof Linking.addEventListener>;
    });
    const save = jest.fn(async (_c: Connection) => undefined);
    // Even with a gateway that would accept the demo tokens, nothing signs in.
    await render(<AppRoot deps={deps(save)} />);
    expect(await screen.findByTestId('passkey-sign-in')).toBeTruthy();
    await act(async () => {
      for (const fn of listeners) fn({ url: 'onemind://demo?as=adult' });
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(save).not.toHaveBeenCalled();
    expect(screen.queryByText('Home OneMind')).toBeNull();
    expect(screen.getByTestId('passkey-sign-in')).toBeTruthy();
  });
});

describe('approval notifications open the named card', () => {
  const target = 'act-notification-target';
  const earlier = 'act-other-request';
  const connection: Connection = { mode: 'live', hubUrl: 'https://hub.example', token: 'owner-demo' };
  const lastResponse = jest.mocked(Notifications.getLastNotificationResponseAsync);
  const clearResponse = jest.mocked(Notifications.clearLastNotificationResponse);
  const asOwner = (targetState: 'awaiting_approval' | 'succeeded' = 'awaiting_approval') => {
    const now = Date.now();
    const a = { ...makeActions(now)[0]!, expires_at: new Date(now + 60_000).toISOString() };
    const actions = [
      { ...a, id: earlier, updated_at: new Date(now).toISOString() },
      { ...a, id: target, state: targetState, updated_at: new Date(now - 1_000).toISOString() },
    ];
    const api = Object.assign(mockApi(connection), {
      actions: async () => actions,
      notification: jest.fn(async () => ({ ...makeInbox(now, 'owner')[0]!, action_id: target })),
      approve: jest.fn(),
      deny: jest.fn(),
    });
    return { api, session: { ...deps(), load: async () => connection, makeApi: () => api } };
  };

  async function expectTarget() {
    expect(await screen.findByTestId(`deny-${target}`)).toBeTruthy();
    expect(screen.getByTestId(`expand-${earlier}`)).toBeTruthy();
    expect(screen.queryByTestId(`deny-${earlier}`)).toBeNull();
  }

  afterEach(() => {
    lastResponse.mockResolvedValue(null);
    clearResponse.mockClear();
    jest.restoreAllMocks();
  });

  it('keeps iOS cold-start Review until the navigator is ready', async () => {
    let releaseLink!: (url: string | null) => void;
    const linking = new Promise<string | null>((resolve) => { releaseLink = resolve; });
    jest.spyOn(Linking, 'getInitialURL').mockReturnValue(linking);
    lastResponse.mockResolvedValue({
      actionIdentifier: 'review',
      notification: { request: { identifier: 'ntf-ios-cold', content: { data: { action_id: target } } } },
    } as unknown as Notifications.NotificationResponse);
    clearResponse.mockClear();
    const { api, session } = asOwner();
    await render(<AppRoot deps={session} />);
    await waitFor(() => expect(clearResponse).toHaveBeenCalled());
    expect(screen.queryByTestId('tab-me')).toBeNull();
    await act(async () => releaseLink(null));
    await expectTarget();
    expect(api.approve).not.toHaveBeenCalled();
    expect(api.deny).not.toHaveBeenCalled();
  });

  it('turns a newly fetched iOS inbox approval into an actionable local notification', async () => {
    const { api, session } = asOwner();
    const item = { ...makeInbox(Date.now(), 'owner')[0]!, topic: 'approvals', action_id: target, read_at: null };
    const notifications = jest.spyOn(api, 'notifications').mockResolvedValue([]);
    const schedule = jest.mocked(Notifications.scheduleNotificationAsync);
    schedule.mockClear();

    await render(<AppRoot deps={session} />);
    await waitFor(() => expect(notifications).toHaveBeenCalled());
    await act(async () => undefined);
    expect(schedule).not.toHaveBeenCalled();

    notifications.mockResolvedValue([item]);
    await fireEvent.press(screen.getByTestId('tab-me'));
    await fireEvent.press(await screen.findByTestId('more-Inbox'));
    await act(async () => screen.getByTestId('inbox').props.refreshControl.props.onRefresh());
    await waitFor(() => expect(schedule).toHaveBeenCalledWith({
      identifier: `ntf:${item.id}`,
      content: {
        title: item.title, body: item.body,
        categoryIdentifier: 'approval',
        data: { route: 'approvals', action_id: target },
      },
      trigger: null,
    }));
    expect(api.approve).not.toHaveBeenCalled();
    expect(api.deny).not.toHaveBeenCalled();
  });

  it('opens the requested card from an Android foreground Review and reopens it from another segment', async () => {
    const listeners: ((event: { url: string }) => void)[] = [];
    jest.spyOn(Linking, 'addEventListener').mockImplementation((_type, fn) => {
      listeners.push(fn as (event: { url: string }) => void);
      return { remove: jest.fn() } as unknown as ReturnType<typeof Linking.addEventListener>;
    });
    const { api, session } = asOwner();
    await render(<AppRoot deps={session} />);
    await screen.findByTestId('tab-me');
    const tap = () => act(async () => {
      for (const fn of listeners) fn({ url: `onemind://approvals?review=${target}` });
    });
    await tap();
    await expectTarget();
    await fireEvent.press(screen.getByTestId('segment-Decided'));
    expect(screen.queryByTestId(`deny-${target}`)).toBeNull();
    await tap();
    await expectTarget();
    expect(api.notification).not.toHaveBeenCalled();
    expect(api.approve).not.toHaveBeenCalled();
    expect(api.deny).not.toHaveBeenCalled();
  });

  it('resolves an Android closed-app Review and opens its card from the notification ID', async () => {
    jest.spyOn(Linking, 'getInitialURL').mockResolvedValue('onemind://approvals?review_notification=ntf-android-cold');
    const { api, session } = asOwner();
    await render(<AppRoot deps={session} />);
    await expectTarget();
    expect(api.notification).toHaveBeenCalledWith('ntf-android-cold');
    expect(api.approve).not.toHaveBeenCalled();
    expect(api.deny).not.toHaveBeenCalled();
  });
  it('shows that a reviewed request has closed and keeps other cards collapsed', async () => {
    jest.spyOn(Linking, 'getInitialURL').mockResolvedValue(`onemind://approvals?review=${target}`);
    const { session } = asOwner('succeeded');
    await render(<AppRoot deps={session} />);
    expect(await screen.findByText('This request is no longer waiting for approval.')).toBeTruthy();
    expect(await screen.findByTestId(`expand-${earlier}`)).toBeTruthy();
    expect(screen.queryByTestId(`deny-${earlier}`)).toBeNull();
  });

});
