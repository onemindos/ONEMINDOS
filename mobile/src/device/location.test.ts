// SPDX-License-Identifier: Apache-2.0
import { AppState } from 'react-native';
import { currentPosition, locationPermission, requestLocationPermission } from './location';

const mockLocation = { getPermission: jest.fn(), requestPermission: jest.fn(), currentPosition: jest.fn() };
jest.mock('expo', () => ({ ...jest.requireActual('expo'), requireNativeModule: () => mockLocation }));

const granted = { status: 'granted', granted: true, canAskAgain: true };
const denied = { status: 'denied', granted: false, canAskAgain: true };
const revoked = { status: 'denied', granted: false, canAskAgain: false };

const originalAppState = AppState.currentState;
beforeEach(() => {
  jest.resetAllMocks();
  AppState.currentState = 'active';
});
afterEach(() => { AppState.currentState = originalAppState; });

it('checks location state without requesting access and refuses a reading after revocation', async () => {
  mockLocation.getPermission.mockResolvedValueOnce(granted).mockResolvedValueOnce(denied).mockResolvedValue(revoked);
  await expect(locationPermission()).resolves.toBe('Allowed');
  await expect(locationPermission()).resolves.toBe('Denied');
  await expect(currentPosition()).rejects.toThrow('Location access is off');
  expect(mockLocation.requestPermission).not.toHaveBeenCalled();
  expect(mockLocation.currentPosition).not.toHaveBeenCalled();
});

it('asks for foreground permission only when requested', async () => {
  mockLocation.getPermission.mockResolvedValueOnce(denied).mockResolvedValueOnce(granted);
  await expect(requestLocationPermission()).resolves.toBe('Allowed');
  expect(mockLocation.requestPermission.mock.calls).toEqual([[false]]);
});

it('reports background location unavailable without calling the native adapter', async () => {
  await expect(locationPermission(true)).resolves.toBe('Not available');
  await expect(requestLocationPermission({ background: true })).resolves.toBe('Not available');
  await expect(currentPosition({ background: true })).rejects.toThrow('Background location is not available');
  expect(mockLocation.getPermission).not.toHaveBeenCalled();
  expect(mockLocation.requestPermission).not.toHaveBeenCalled();
  expect(mockLocation.currentPosition).not.toHaveBeenCalled();
});

it('rejects foreground readings while inactive', async () => {
  const previous = AppState.currentState;
  AppState.currentState = 'background';
  try {
    await expect(currentPosition()).rejects.toThrow('Open OneMind');
    expect(mockLocation.currentPosition).not.toHaveBeenCalled();
  } finally {
    AppState.currentState = previous;
  }
});

it('reports a denied request, and does not prompt when the system blocked it', async () => {
  mockLocation.getPermission.mockResolvedValueOnce(denied).mockResolvedValueOnce(denied);
  await expect(requestLocationPermission()).resolves.toBe('Denied');
  expect(mockLocation.requestPermission).toHaveBeenCalledTimes(1);
  mockLocation.requestPermission.mockClear();
  mockLocation.getPermission.mockResolvedValue(revoked);
  await expect(requestLocationPermission()).resolves.toBe('Blocked');
  expect(mockLocation.requestPermission).not.toHaveBeenCalled();
});
