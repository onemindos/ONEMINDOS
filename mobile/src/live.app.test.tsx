// SPDX-License-Identifier: Apache-2.0
// MOB-LIVE-01: walks the whole app (Connect → Home → Apps → Approvals → Settings) against a REAL gateway.
// Skipped unless ONEMIND_LIVE_HUB is set (see src/api/live.test.ts).
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import App from '../App';
import { nodeFetch } from './test/nodeFetch';

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

const hub = process.env.ONEMIND_LIVE_HUB;
const token = process.env.ONEMIND_LIVE_TOKEN ?? 'dev-owner-token-change-me';
const d = hub ? describe : describe.skip;

d('the app on a real hub', () => {
  beforeAll(() => {
    (globalThis as { fetch: unknown }).fetch = nodeFetch;
    // The live-update stream uses XMLHttpRequest, which jest does not have; without it the app polls.
    (globalThis as { XMLHttpRequest: unknown }).XMLHttpRequest = class {
      open() {}
      setRequestHeader() {}
      send() {}
      abort() {}
    };
  });

  it('connects with a token and shows real Home, Apps, Approvals and Settings', async () => {
    await render(<App />);
    await fireEvent.changeText(await screen.findByTestId('hub-url'), hub!);
    await fireEvent.press(screen.getByTestId('use-token'));
    await fireEvent.changeText(screen.getByTestId('token'), token);
    await fireEvent.press(screen.getByTestId('connect'));
    expect(await screen.findByTestId('home', {}, { timeout: 8000 })).toBeTruthy();
    // Real data, not the demo's.
    expect(screen.queryByText('Home OneMind')).toBeNull();

    await fireEvent.press(screen.getByText('Apps'));
    expect(await screen.findByTestId('apps')).toBeTruthy();
    // The hub's own catalog (the Market seed), not the demo's six apps.
    expect(await screen.findByTestId('app-actual-budget', {}, { timeout: 8000 })).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(/Could not read/)).toBeNull());

    await fireEvent.press(screen.getByText('Approvals'));
    expect(await screen.findByTestId('approvals')).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(/Could not read/)).toBeNull());

    await fireEvent.press(screen.getByTestId('tab-me'));
    await fireEvent.press(await screen.findByTestId('more-Settings'));
    expect(await screen.findByTestId('settings')).toBeTruthy();
  });
});
