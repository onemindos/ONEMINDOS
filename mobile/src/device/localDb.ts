// SPDX-License-Identifier: Apache-2.0
import { openDatabaseAsync, type SQLiteDatabase } from 'expo-sqlite';
import { Directory, Paths } from './files';

/** Index 0 creates schema version 1. Append migrations in order and keep them transaction-safe. */
export type LocalMigration = (db: Pick<SQLiteDatabase, 'execAsync' | 'runAsync' | 'getFirstAsync' | 'getAllAsync'>) => Promise<void>;
const databases = new Map<string, SQLiteDatabase>();
let queue: Promise<unknown> = Promise.resolve();

function serialize<T>(work: () => Promise<T>): Promise<T> {
  const result = queue.then(work);
  queue = result.catch(() => undefined);
  return result;
}

const directory = () => new Directory(Paths.document, 'onemind-app-databases');

export function openLocalDb(appId: string, migrations: readonly LocalMigration[]): Promise<SQLiteDatabase> {
  return serialize(async () => {
    if (!/^[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?$/.test(appId)) throw new Error('Invalid local database app id.');
    const dir = directory();
    dir.create({ idempotent: true, intermediates: true });
    const existing = databases.get(appId);
    const db = existing ?? await openDatabaseAsync(`${appId}.db`, { useNewConnection: true }, dir.uri);
    try {
      await db.withExclusiveTransactionAsync(async txn => {
        const version = (await txn.getFirstAsync<{ user_version: number }>('PRAGMA user_version'))?.user_version ?? 0;
        if (version > migrations.length) throw new Error('This local database was created by a newer version.');
        for (let i = version; i < migrations.length; i++) {
          await migrations[i]!(txn);
          await txn.execAsync(`PRAGMA user_version = ${i + 1}`);
        }
      });
    } catch (error) {
      if (!existing) await db.closeAsync();
      throw error;
    }
    databases.set(appId, db);
    return db;
  });
}

export function wipeLocalDatabases(): Promise<void> {
  return serialize(async () => {
    for (const [id, db] of databases) {
      await db.closeAsync();
      databases.delete(id);
    }
    const dir = directory();
    if (dir.exists) dir.delete();
  });
}
