// SPDX-License-Identifier: Apache-2.0
import { openDatabaseAsync, type SQLiteDatabase } from 'expo-sqlite';
import { requireNativeModule } from 'expo';
import { Platform } from 'react-native';
import { Directory, File, Paths } from './files';

/** Index 0 creates schema version 1. Append migrations in order and keep them transaction-safe. */
export type LocalMigration = (db: Pick<SQLiteDatabase, 'execAsync' | 'runAsync' | 'getFirstAsync' | 'getAllAsync'>) => Promise<void>;
const databases = new Map<string, SQLiteDatabase>();
let unlocked = false;
let queue: Promise<unknown> = Promise.resolve();

function serialize<T>(work: () => Promise<T>): Promise<T> {
  const result = queue.then(work);
  queue = result.catch(() => undefined);
  return result;
}

const directory = () => new Directory(Paths.document, 'onemind-app-databases');
const ownerFile = (dir: Directory) => new File(dir, '.owner');
const pendingFile = (dir: Directory) => new File(dir, '.wipe-pending');

async function privateDirectory(): Promise<Directory> {
  const dir = directory();
  if (Platform.OS === 'ios') {
    await requireNativeModule<{ excludeDatabaseDirectoryFromBackup(): Promise<void> }>('OneMindPrivateFiles')
      .excludeDatabaseDirectoryFromBackup();
  } else {
    dir.create({ idempotent: true, intermediates: true });
  }
  return dir;
}

async function closeDatabases() {
  for (const [id, db] of databases) {
    await db.closeAsync();
    databases.delete(id);
  }
}

async function finishWipe(dir: Directory, pending: File) {
  await closeDatabases();
  for (const entry of dir.list()) {
    if (entry.uri !== pending.uri) entry.delete();
  }
  pending.delete();
}

/** Recover an interrupted wipe before serving any database, even on a signed-out launch. */
export function resumeLocalDatabases(account?: string): Promise<void> {
  return serialize(async () => {
    unlocked = false;
    const dir = directory();
    if (!dir.exists) return;
    const pending = pendingFile(dir);
    if (pending.exists) await finishWipe(dir, pending);
    if (!account) return;
    const owner = ownerFile(await privateDirectory());
    unlocked = owner.exists && owner.textSync() === account;
  });
}

/** The session calls this only for an identity verified by the hub. */
export function activateLocalDatabases(account: string): Promise<void> {
  return serialize(async () => {
    unlocked = false;
    const dir = await privateDirectory();
    const pending = pendingFile(dir);
    const owner = ownerFile(dir);
    if (pending.exists || (owner.exists ? owner.textSync() !== account : dir.list().length > 0)) {
      if (!pending.exists) pending.create();
      await finishWipe(dir, pending);
    }
    if (!owner.exists) {
      owner.create();
      owner.writeSync(account);
    }
    unlocked = true;
  });
}

export function lockLocalDatabases(): Promise<void> {
  return serialize(async () => {
    unlocked = false;
    await closeDatabases();
  });
}


/** Migrations run inside the serialize queue: a migration must not call openLocalDb (it would wait on itself). */
export function openLocalDb(appId: string, migrations: readonly LocalMigration[]): Promise<SQLiteDatabase> {
  return serialize(async () => {
    if (!/^[a-z0-9](?:[a-z0-9-]{0,57}[a-z0-9])?$/.test(appId)) throw new Error('Invalid local database app id.');
    if (!unlocked) throw new Error('Sign in to use local app data.');
    const dir = directory();
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
    unlocked = false;
    const dir = directory();
    if (!dir.exists) return;
    // Record the intent first and without the native backup call, so a failure there cannot skip the wipe.
    const pending = pendingFile(dir);
    if (!pending.exists) pending.create();
    await finishWipe(dir, pending);
  });
}
