// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen } from '@testing-library/react-native';
import { JoinScanner } from './JoinScanner.android';

const mockTakePicture = jest.fn();
const mockReadPhoto = jest.fn();
const mockDeleteFile = jest.fn();

jest.mock('expo-camera', () => ({
  useCameraPermissions: () => [{ granted: true }, jest.fn()],
  CameraView: ({ ref, onCameraReady }: { ref: { current: unknown }; onCameraReady: () => void }) => {
    const React = jest.requireActual('react');
    React.useImperativeHandle(ref, () => ({ takePictureAsync: mockTakePicture }));
    React.useEffect(() => { onCameraReady(); }, []);
    return null;
  },
}));
jest.mock('expo', () => ({ ...jest.requireActual('expo'), requireNativeModule: () => ({ readCameraPhoto: mockReadPhoto }) }));
jest.mock('expo-file-system', () => ({ File: jest.fn((uri: string) => ({ uri, delete: mockDeleteFile })) }));

beforeEach(() => {
  jest.clearAllMocks();
  mockTakePicture.mockResolvedValue({ uri: 'file:///cache/join.jpg' });
});

it('uses the offline decoder and deletes the temporary photo before handing the join code over', async () => {
  mockReadPhoto.mockResolvedValue('join-code');
  const onCode = jest.fn(() => expect(mockDeleteFile).toHaveBeenCalledTimes(1));
  await render(<JoinScanner onCode={onCode} onCancel={jest.fn()} />);
  await fireEvent.press(screen.getByRole('button', { name: 'Scan code' }));
  expect(mockReadPhoto).toHaveBeenCalledWith('file:///cache/join.jpg');
  expect(onCode).toHaveBeenCalledWith('join-code');
  await fireEvent.press(screen.getByRole('button', { name: 'Scan code' }));
  expect(onCode).toHaveBeenCalledTimes(1);
});

it('cleans up when no code is found and allows another scan', async () => {
  mockReadPhoto.mockResolvedValueOnce(null).mockResolvedValueOnce('join-code');
  const onCode = jest.fn();
  await render(<JoinScanner onCode={onCode} onCancel={jest.fn()} />);
  await fireEvent.press(screen.getByRole('button', { name: 'Scan code' }));
  expect(screen.getByText(/No join code found/)).toBeTruthy();
  expect(onCode).not.toHaveBeenCalled();
  await fireEvent.press(screen.getByRole('button', { name: 'Scan code' }));
  expect(onCode).toHaveBeenCalledWith('join-code');
  expect(mockDeleteFile).toHaveBeenCalledTimes(2);
});

it('discards a scan that finishes after the user cancels', async () => {
  let finishScan: (value: string) => void = () => undefined;
  mockReadPhoto.mockImplementationOnce(() => new Promise<string>(resolve => { finishScan = resolve; }));
  const onCode = jest.fn();
  const onCancel = jest.fn();
  await render(<JoinScanner onCode={onCode} onCancel={onCancel} />);
  await fireEvent.press(screen.getByRole('button', { name: 'Scan code' }));
  await fireEvent.press(screen.getByRole('button', { name: 'Cancel' }));
  await act(async () => { finishScan('join-code'); });
  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onCode).not.toHaveBeenCalled();
  expect(mockDeleteFile).toHaveBeenCalledTimes(1);
});
