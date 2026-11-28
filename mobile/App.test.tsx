// SPDX-License-Identifier: Apache-2.0
// Smoke test of the whole shell: Connect → sign in with a token → tabs → Me → Inbox. The gateway is the
// in-memory fake (src/test/mockHub.ts) handed in for the test; the app itself has no demo to open.
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { Linking } from 'react-native';
import App, { AppRoot } from './App';
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
