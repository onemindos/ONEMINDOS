// SPDX-License-Identifier: Apache-2.0
import { openDatabaseAsync } from 'expo-sqlite';
import { activateLocalDatabases, lockLocalDatabases, openLocalDb, resumeLocalDatabases, wipeLocalDatabases } from './localDb';

const mockEntries = new Map<string, string>();
const mockDelete = jest.fn((name: string) => mockEntries.delete(name));
jest.mock('expo-sqlite', () => ({ openDatabaseAsync: jest.fn() }));
const mockExclude = jest.fn(async () => undefined);
jest.mock('expo', () => ({
  requireNativeModule: () => ({ excludeDatabaseDirectoryFromBackup: () => mockExclude() }),
}));
jest.mock('./files', () => {
  function entry(name: string) {
    return {
      uri: name,
      get exists() { return mockEntries.has(name); },
      delete: () => mockDelete(name),
      create: () => mockEntries.set(name, ''),
      textSync: () => mockEntries.get(name),
      writeSync: (value: string) => mockEntries.set(name, value),
    };
  }
  return {
    Directory: jest.fn(() => ({
      uri: 'file:///private/app-databases', exists: true, create: jest.fn(),
      list: () => [...mockEntries.keys()].map(entry),
    })),
    File: jest.fn((_directory, name: string) => entry(name)),
    Paths: { document: 'file:///private' },
  };
});

function database() {
  let version = 0;
  const transaction = {
    getFirstAsync: jest.fn(async () => ({ user_version: version })),
    execAsync: jest.fn(async (sql: string) => { version = Number(sql.split(' = ')[1]); }),
  };
  return { withExclusiveTransactionAsync: jest.fn(async run => run(transaction)), closeAsync: jest.fn() };
}

beforeEach(async () => {
  await wipeLocalDatabases();
  jest.clearAllMocks();
  await activateLocalDatabases('owner');
});

it('isolates apps and migrates a shared open handle only once', async () => {
  const notes = database();
  const recorder = database();
  jest.mocked(openDatabaseAsync).mockResolvedValueOnce(notes as never).mockResolvedValueOnce(recorder as never);
  const first = jest.fn();
  const second = jest.fn();
  const [a, b] = await Promise.all([openLocalDb('notes', [first]), openLocalDb('notes', [first, second])]);
  expect(a).toBe(b);
  expect(first).toHaveBeenCalledTimes(1);
  expect(second).toHaveBeenCalledTimes(1);
  expect(await openLocalDb('recorder', [])).toBe(recorder);
  expect(jest.mocked(openDatabaseAsync).mock.calls.map(([file]) => file)).toEqual(['notes.db', 'recorder.db']);
  await expect(openLocalDb('../notes', [])).rejects.toThrow('Invalid local database app id');
});

it('closes connections and removes files, including databases from previous launches', async () => {
  const notes = database();
  jest.mocked(openDatabaseAsync).mockResolvedValueOnce(notes as never);
  await openLocalDb('notes', []);
  mockEntries.set('old.db', '');
  await wipeLocalDatabases();
  expect(notes.closeAsync).toHaveBeenCalledTimes(1);
  expect(mockEntries.size).toBe(0);
});

it('retries an interrupted wipe on startup before allowing any database to open', async () => {
  mockEntries.set('outbox.db', 'pending edit');
  mockDelete.mockImplementationOnce(() => { throw new Error('disk error'); });
  await expect(wipeLocalDatabases()).rejects.toThrow('disk error');
  expect(mockEntries.has('.wipe-pending')).toBe(true);
  await expect(openLocalDb('notes', [])).rejects.toThrow('Sign in');
  await resumeLocalDatabases('owner');
  expect(mockEntries.size).toBe(0);
  await expect(openLocalDb('notes', [])).rejects.toThrow('Sign in');
  expect(openDatabaseAsync).not.toHaveBeenCalled();
});

it('retains an expired account’s outbox and wipes it only when a different account connects', async () => {
  mockEntries.set('outbox.db', 'pending edit');
  await lockLocalDatabases();
  await expect(openLocalDb('notes', [])).rejects.toThrow('Sign in');
  await resumeLocalDatabases();
  await activateLocalDatabases('owner');
  expect(mockEntries.get('outbox.db')).toBe('pending edit');
  await activateLocalDatabases('another account');
  expect(mockEntries.has('outbox.db')).toBe(false);
});

it('records the wipe marker and removes the data even when the iOS backup exclusion call throws', async () => {
  mockEntries.set('outbox.db', 'pending edit');
  mockExclude.mockRejectedValueOnce(new Error('native failure'));
  await wipeLocalDatabases();
  expect(mockEntries.size).toBe(0);
  await expect(openLocalDb('notes', [])).rejects.toThrow('Sign in');
});
