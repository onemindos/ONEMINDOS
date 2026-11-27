// SPDX-License-Identifier: Apache-2.0
import { AppState } from 'react-native';
import { currentPosition, locationPermission, requestLocationPermission } from './location';

const mockLocation = { getPermission: jest.fn(), requestPermission: jest.fn(), currentPosition: jest.fn() };
jest.mock('expo', () => ({ ...jest.requireActual('expo'), requireNativeModule: () => mockLocation }));

const granted = { status: 'granted', granted: true, canAskAgain: true };
const denied = { status: 'denied', granted: false, canAskAgain: true };
const revoked = { status: 'denied', granted: false, canAskAgain: false };

beforeEach(() => jest.resetAllMocks());

it('checks location state without requesting access and refuses a reading after revocation', async () => {
  mockLocation.getPermission.mockResolvedValueOnce(granted).mockResolvedValueOnce(denied).mockResolvedValue(revoked);
  await expect(locationPermission()).resolves.toBe('Allowed');
  await expect(locationPermission()).resolves.toBe('Denied');
  await expect(locationPermission(true)).resolves.toBe('Blocked');
  await expect(currentPosition({ background: true })).rejects.toThrow('Location access is off');
  expect(mockLocation.requestPermission).not.toHaveBeenCalled();
  expect(mockLocation.currentPosition).not.toHaveBeenCalled();
});

it('only asks for background access explicitly, after foreground access is granted', async () => {
  mockLocation.getPermission.mockResolvedValueOnce(denied).mockResolvedValueOnce(denied)
    .mockResolvedValueOnce(granted).mockResolvedValueOnce(granted).mockResolvedValueOnce(denied).mockResolvedValue(granted);
  await expect(requestLocationPermission({ background: true })).resolves.toBe('Denied');
  await expect(requestLocationPermission()).resolves.toBe('Allowed');
  await expect(requestLocationPermission({ background: true })).resolves.toBe('Allowed');
  expect(mockLocation.requestPermission.mock.calls).toEqual([[false], [true]]);
});

it('rejects foreground reading while inactive and passes an explicit background grant to the adapter', async () => {
  const previous = AppState.currentState;
  AppState.currentState = 'background';
  try {
    const fix = { latitude: 1, longitude: 2, accuracyMeters: 3, timestamp: 4 };
    mockLocation.getPermission.mockResolvedValue(granted);
    mockLocation.currentPosition.mockResolvedValue(fix);
    await expect(currentPosition()).rejects.toThrow('Open OneMind');
    await expect(currentPosition({ background: true })).resolves.toEqual(fix);
    expect(mockLocation.currentPosition.mock.calls).toEqual([[true]]);
  } finally {
    AppState.currentState = previous;
  }
});
