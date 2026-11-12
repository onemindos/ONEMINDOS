// SPDX-License-Identifier: Apache-2.0
// Smoke test of the whole shell on the demo backend: Connect → demo owner → tabs → More → Inbox.
import { fireEvent, render, screen } from '@testing-library/react-native';
import App from './App';

// eslint-disable-next-line @typescript-eslint/no-require-imports
jest.mock('react-native-safe-area-context', () => require('react-native-safe-area-context/jest/mock').default);

describe('app shell', () => {
  it('starts at Connect with passkey sign-in first, opens the demo, and reaches the Inbox through More', async () => {
    await render(<App />);
    expect(await screen.findByTestId('brand-mark')).toBeTruthy();
    expect(screen.getByTestId('passkey-sign-in')).toBeTruthy();
    expect(screen.queryByTestId('token')).toBeNull();
    await fireEvent.press(screen.getByTestId('demo-owner-demo'));
    expect(await screen.findByText('Home OneMind')).toBeTruthy();
    await fireEvent.press(screen.getByText('More'));
    await fireEvent.press(await screen.findByTestId('more-Inbox'));
    expect(await screen.findByTestId('ntf-ntf_demo_01')).toBeTruthy();
  });
});
