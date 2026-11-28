// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Linking } from 'react-native';
import { PermissionsScreen } from './PermissionsScreen';

jest.mock('@react-navigation/native', () => ({
  useFocusEffect: (effect: () => void) => jest.requireActual('react').useEffect(effect, [effect]),
}));
jest.mock('../device/camera', () => ({ cameraPermission: () => Promise.resolve('Denied') }));
jest.mock('../device/mic', () => ({ microphonePermission: () => Promise.resolve('Not asked') }));
jest.mock('../device/files', () => ({ photosPermission: () => Promise.resolve('Selected items only') }));
jest.mock('../device/location', () => ({ locationPermission: (background?: boolean) => Promise.resolve(background ? 'Not available' : 'Blocked') }));
jest.mock('../device/background', () => ({ backgroundPermission: () => Promise.resolve('Restricted') }));
jest.mock('../device/notifications', () => ({ notificationPermission: () => Promise.resolve('Allowed') }));

it('shows why permissions are used, the OS states, and opens phone settings when asked', async () => {
  const settings = jest.spyOn(Linking, 'openSettings').mockResolvedValue(undefined);
  try {
    await render(<PermissionsScreen />);
    expect(await screen.findByText('Selected items only')).toBeOnTheScreen();
    expect(screen.getByText('Denied')).toBeOnTheScreen();
    expect(screen.getByText('Not available')).toBeOnTheScreen();
    expect(screen.queryByRole('button', { name: /background location/i })).toBeNull();
    expect(screen.getByRole('button', { name: 'Open phone settings for location' })).toBeOnTheScreen();
    expect(screen.getByText('Private to OneMind')).toBeOnTheScreen();
    expect(screen.getByText('Capture sound when you start a recording.')).toBeOnTheScreen();
    expect(settings).not.toHaveBeenCalled();
    await fireEvent.press(screen.getByRole('button', { name: 'Open phone settings for microphone' }));
    await waitFor(() => expect(settings).toHaveBeenCalledTimes(1));
  } finally {
    settings.mockRestore();
  }
});
