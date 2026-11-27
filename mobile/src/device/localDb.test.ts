// SPDX-License-Identifier: Apache-2.0
import { openDatabaseAsync } from 'expo-sqlite';
import { openLocalDb, wipeLocalDatabases } from './localDb';

const mockDelete = jest.fn();
jest.mock('expo-sqlite', () => ({ openDatabaseAsync: jest.fn() }));
jest.mock('./files', () => ({
  Directory: jest.fn(() => ({ uri: 'file:///private/app-databases', exists: true, create: jest.fn(), delete: mockDelete })),
  Paths: { document: 'file:///private' },
}));

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

it('closes connections and removes the database directory, including files from previous launches', async () => {
  const notes = database();
  jest.mocked(openDatabaseAsync).mockResolvedValueOnce(notes as never);
  await openLocalDb('notes', []);
  await wipeLocalDatabases();
  expect(notes.closeAsync).toHaveBeenCalledTimes(1);
  expect(mockDelete).toHaveBeenCalledTimes(1);
});
