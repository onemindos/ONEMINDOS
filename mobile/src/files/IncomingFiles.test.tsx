// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import * as SecureStore from 'expo-secure-store';
import { Features, OP, type OneMindApi } from '../api/client';
import { ApiError } from '../api/types';
import { LOCK_KEY, LockProvider, useIsLocked } from '../lock/LockProvider';
import { useSignedIn } from '../session';
import { IncomingFiles } from './IncomingFiles';
import { canResolve, stagedFiles, useFileShare } from './incoming';
import { deliverShare, discardShare, readShare, shareDirectory, stageShare } from './shareQueue';
import type { ResolvedSharePayload } from 'expo-sharing';

jest.mock('../data', () => ({ useHubData: () => ({ refreshing: false }) }));
jest.mock('../lock/LockProvider', () => ({ ...jest.requireActual('../lock/LockProvider'), useIsLocked: jest.fn(() => false) }));
jest.mock('../session', () => ({ useSignedIn: jest.fn() }));
jest.mock('./incoming', () => ({ ...jest.requireActual('./incoming'), useFileShare: jest.fn() }));
jest.mock('./shareQueue', () => ({
  shareDirectory: jest.fn(), readShare: jest.fn(), stageShare: jest.fn(), deliverShare: jest.fn(), discardShare: jest.fn(),
}));
jest.mock('./shareBackground', () => ({ scheduleShare: jest.fn(async () => {}), unscheduleShare: jest.fn(async () => {}) }));

const files = [{ name: 'photo.jpg', uri: 'file:///cache/photo' }, { name: 'paper.pdf', uri: 'file:///cache/pdf' }];
const destination = { root: 'shared', path: '/Inbox' };
const job = { files: files.map(f => f.name), destination };
const dir = { uri: 'file:///confirmed' };
const clear = jest.fn();
const writable = { root: 'shared', name: 'Shared files', path: '/', writable: true };

beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(useIsLocked).mockReturnValue(false);
  jest.mocked(readShare).mockResolvedValue(undefined);
  jest.mocked(deliverShare).mockResolvedValue(undefined);
  jest.mocked(useFileShare).mockReturnValue({ incoming: { key: 'photos', files }, clear });
  jest.mocked(shareDirectory).mockResolvedValue(dir as Awaited<ReturnType<typeof shareDirectory>>);
  jest.mocked(stageShare).mockResolvedValue(job);
  jest.mocked(useSignedIn).mockReturnValue({
    connection: { mode: 'live', hubUrl: 'https://hub.test', token: 'test' }, principal: { id: 'owner', kind: 'person', role: 'owner' },
    features: new Features([OP.filesUploads, OP.filesRoots, OP.filesList], 'openapi'), label: 'hub.test',
    api: { filesRoots: async () => [writable, { ...writable, root: 'readonly', name: 'Read only', writable: false }],
      filesList: async (_root: string, path: string) => path === '/' ? [{ name: 'Inbox', type: 'dir' }] : [] } as unknown as OneMindApi,
  } as ReturnType<typeof useSignedIn>);
});

it('requires confirming the displayed files and writable subfolder before staging or sending', async () => {
  await render(<IncomingFiles />);
  expect(await screen.findByText('Shared files')).toBeTruthy();
  expect(screen.queryByText('Read only')).toBeNull();
  expect(screen.queryByText('Send to this folder')).toBeNull();
  await fireEvent.press(screen.getByText('Shared files'));
  await fireEvent.press(await screen.findByText('Inbox'));
  expect(await screen.findByText('Shared files /Inbox')).toBeTruthy();
  expect(deliverShare).not.toHaveBeenCalled();
  expect(stageShare).not.toHaveBeenCalled();
  await fireEvent.press(await screen.findByText('Send to this folder'));
  await waitFor(() => expect(deliverShare).toHaveBeenCalledTimes(1));
  expect(stageShare).toHaveBeenCalledWith(dir, files, destination);
  expect(clear).toHaveBeenCalledWith('photos');
});

it('can cancel a share without creating an upload', async () => {
  await render(<IncomingFiles />);
  await fireEvent.press(await screen.findByText('Cancel'));
  expect(clear).toHaveBeenCalledWith('photos');
  expect(stageShare).not.toHaveBeenCalled();
  expect(deliverShare).not.toHaveBeenCalled();
});

it('keeps a refused batch available to discard and explains the gateway quota', async () => {
  jest.mocked(readShare).mockResolvedValue(job);
  jest.mocked(deliverShare).mockRejectedValue(new ApiError(413, 'conflict', 'quota'));
  await render(<IncomingFiles />);
  await fireEvent.press(await screen.findByText('Resume sending'));
  expect(await screen.findByText(/not enough space/)).toBeTruthy();
  await fireEvent.press(screen.getByText('Discard remaining files'));
  expect(discardShare).toHaveBeenCalledWith(dir);
  expect(stageShare).not.toHaveBeenCalled();
});

it('rejects Android shares pointing into this app and changed batches', () => {
  const raw = { value: 'content://provider.test/document/1', shareType: 'file' as const, mimeType: 'application/pdf' };
  expect(canResolve([raw], true)).toBe(true);
  expect(canResolve([{ ...raw, shareType: 'video', mimeType: 'video/mp4' }], true)).toBe(true);
  expect(canResolve([{ ...raw, shareType: 'url' }], true)).toBe(false);
  expect(canResolve([{ ...raw, shareType: 'text' }], true)).toBe(false);
  for (const value of ['file:///private/file', 'https://remote.test/document', 'content://com.onemindos.mobile.FileSystemFileProvider/data']) {
    expect(canResolve([{ ...raw, value }], true)).toBe(false);
  }
  const resolved = { ...raw, originalName: 'paper.pdf', contentUri: 'file:///cache/paper.pdf' } as ResolvedSharePayload;
  expect(stagedFiles([raw], [resolved])).toEqual([{ name: 'paper.pdf', uri: resolved.contentUri }]);
  expect(() => stagedFiles([raw], [{ ...resolved, value: 'content://provider.test/document/2' }])).toThrow();
});

it('registers Android single-document and mixed-batch shares without advertising raw single text', () => {
  const { expo } = require('../../app.json');
  const [, options] = expo.plugins.find((entry: unknown) => Array.isArray(entry) && entry[0] === 'expo-sharing');
  expect(options.android).toEqual({
    enabled: true, singleShareMimeTypes: ['image/*', 'application/*', 'audio/*', 'video/*'], multipleShareMimeTypes: ['*/*'],
  });
});

it('shows nothing while the app is locked (a Modal would draw above the lock), and the sheet opens after the unlock', async () => {
  jest.mocked(useIsLocked).mockReturnValue(true);
  const view = await render(<IncomingFiles />);
  expect(screen.queryByText('Shared files')).toBeNull();
  expect(shareDirectory).not.toHaveBeenCalled(); // no folder listing or upload can start behind the lock
  jest.mocked(useIsLocked).mockReturnValue(false);
  await view.rerender(<IncomingFiles />);
  expect(await screen.findByText('Shared files')).toBeTruthy();
  expect(clear).not.toHaveBeenCalled(); // the shared files were kept for after the unlock
});

it('keeps an incoming share out of the native modal while the lock preference is loading', async () => {
  const actual = jest.requireActual<typeof import('../lock/LockProvider')>('../lock/LockProvider');
  const read = jest.mocked(SecureStore.getItemAsync);
  const previous = read.getMockImplementation()!;
  let finish!: (value: string | null) => void;
  read.mockImplementation((key, options) => key === LOCK_KEY
    ? new Promise((resolve) => { finish = resolve; })
    : previous(key, options));
  jest.mocked(useIsLocked).mockImplementation(actual.useIsLocked);
  try {
    await render(<LockProvider><IncomingFiles /></LockProvider>);
    expect(screen.getByTestId('app-lock-checking')).toBeTruthy();
    expect(screen.queryByText('Send to OneMind', { includeHiddenElements: true })).toBeNull();
    expect(shareDirectory).not.toHaveBeenCalled();
    finish(null);
    expect(await screen.findByText('Shared files')).toBeTruthy();
    expect(clear).not.toHaveBeenCalled();
  } finally {
    read.mockImplementation(previous);
  }
});
