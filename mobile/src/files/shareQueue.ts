// SPDX-License-Identifier: Apache-2.0
import { digestStringAsync, CryptoDigestAlgorithm, randomUUID } from 'expo-crypto';
import { Directory, File, Paths } from '../device/files';
import type { OneMindApi, TusTransport } from '../api/client';
import { ApiError } from '../api/types';
import { uploadLocalFile, uploadProblem } from '../lib/filesTransfer';
import { asLocalFile } from './native';

export type SharedFile = { name: string; uri: string };
export type Destination = { root: string; path: string };
export type ShareJob = { files: string[]; destination: Destination; error?: string };

export async function shareDirectory(hub: string, person: string) {
  const id = await digestStringAsync(CryptoDigestAlgorithm.SHA256, JSON.stringify([hub, person]));
  return new Directory(Paths.document, 'onemind-incoming', id);
}

export async function readShare(dir: Directory): Promise<ShareJob | undefined> {
  const manifest = new File(dir, 'confirmed.json');
  if (!manifest.exists) return;
  const job: ShareJob = JSON.parse(await manifest.text());
  const paused = new File(dir, 'paused');
  if (paused.exists) job.error = await paused.text();
  return job;
}

/** Publish the confirmed batch only after every attachment is safely outside the share cache. */
export async function stageShare(dir: Directory, files: SharedFile[], destination: Destination) {
  if (!files.length || dir.exists) throw new Error('Finish the previous share first.');
  const staging = new Directory(dir.parentDirectory, dir.name + '-staging');
  if (staging.exists) staging.delete();
  staging.create({ intermediates: true });
  try {
    for (const [i, item] of files.entries()) {
      const source = new File(item.uri);
      if (!source.exists) throw new Error('The shared file is no longer available. Share it again.');
      await source.copy(new File(staging, String(i)));
    }
    const job: ShareJob = { files: files.map(f => f.name), destination };
    await new File(staging, 'confirmed.json').write(JSON.stringify(job));
    staging.rename(dir.name);
    return job;
  } catch (error) {
    if (staging.exists) staging.delete();
    throw error;
  }
}

/** Native iOS background URLSession needs a disk-backed body. Keep each PATCH within the tus chunk size. */
function nativePatch(dir: Directory): TusTransport {
  return async (url, headers, bytes) => {
    const chunk = new File(dir, 'patch-' + randomUUID());
    try {
      await chunk.write(bytes);
      const r = await chunk.upload(url, { httpMethod: 'PATCH', headers, sessionType: 'background' });
      return new Response(r.body || null, { status: r.status, headers: r.headers });
    } finally {
      if (chunk.exists) chunk.delete();
    }
  };
}

/** The scheduler and the mounted screen can wake together. Both await the same transfer. */
const active = new Map<string, Promise<void>>();

export function discardShare(dir: Directory) {
  if (active.has(dir.uri)) throw new Error('A transfer is running. Wait for it to finish.');
  if (dir.exists) dir.delete();
}

export function deliverShare(api: OneMindApi, dir: Directory, retry = false): Promise<void> {
  const key = dir.uri;
  const existing = active.get(key);
  if (existing) return existing;
  const task = deliver(api, dir, retry).finally(() => active.delete(key));
  active.set(key, task);
  return task;
}

async function deliver(api: OneMindApi, dir: Directory, retry: boolean) {
  const job = await readShare(dir);
  if (!job) return;
  const paused = new File(dir, 'paused');
  if (paused.exists) {
    if (!retry) throw new Error(job.error);
    paused.delete();
  }
  for (const [i, name] of job.files.entries()) {
    const local = new File(dir, String(i));
    const done = new File(dir, 'done-' + i);
    if (done.exists) continue;
    if (!local.exists) throw new Error('The saved attachment is missing. Discard this batch and share it again.');
    const checkpoint = new File(dir, 'upload-' + i);
    const url = checkpoint.exists ? await checkpoint.text() : undefined;
    try {
      await uploadLocalFile(api, asLocalFile(local, name), job.destination.root, job.destination.path, undefined, {
        url,
        created: async (location) => {
          const temp = new File(dir, 'location.tmp');
          await temp.write(location);
          temp.rename(checkpoint.name);
        },
        transport: nativePatch(dir),
      });
    } catch (error) {
      if (error instanceof ApiError && [403, 404, 409, 413].includes(error.status)
          && error.reason !== 'upload_busy' && error.reason !== 'offset_mismatch') {
        if (error.reason === 'upload_expired' && checkpoint.exists) checkpoint.delete();
        await paused.write(uploadProblem(error));
      }
      throw error;
    }
    done.create();
    local.delete();
  }
  dir.delete();
}
