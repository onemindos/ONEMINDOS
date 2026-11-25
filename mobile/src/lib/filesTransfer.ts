// SPDX-License-Identifier: Apache-2.0
// Phone parity, files: send one local file into a folder the person may write, in resumable tus chunks
// (docs/leap/core/FILES.md section 3). Pure logic over the typed client, so it is tested without a phone.
import type { OneMindApi, TusTransport } from '../api/client';
import { ApiError } from '../api/types';

export const CHUNK_BYTES = 4 * 1024 * 1024;
const ATTEMPTS = 4;

/** A file on the phone, read in slices so a large video never sits in memory whole. */
export interface LocalFile {
  name: string;
  size: number;
  read(offset: number, length: number): Promise<Uint8Array>;
  /** Hex sha-256 of the whole file; when present the hub checks it and a mismatch deletes the upload. */
  sha256?(): Promise<string>;
}

/** What the phone itself does: choose, fetch to disk, hand to the share sheet. Native in the app, a fake in tests. */
export interface FilesDevice {
  pick(): Promise<LocalFile | undefined>;
  /** Streams the file to the phone's cache and returns its local address. */
  download(req: { url: string; headers: Record<string, string> }, name: string): Promise<string>;
  share(localUri: string, name: string): Promise<void>;
}

/** The names the hub refuses or that would escape a folder; the hub checks again, this only gives a plain message early. */
export function badFileName(name: string): string | undefined {
  if (!name.trim()) return 'This file has no name.';
  if (/[\\/]/.test(name) || name === '.' || name === '..') return 'File names cannot contain slashes.';
  return undefined;
}

/** Upload errors a person can act on, in plain words. */
export function uploadProblem(e: unknown): string {
  if (!(e instanceof ApiError)) return String(e);
  if (e.status === 403) return 'You can look in this folder but not add files to it.';
  if (e.status === 409 && e.reason === 'digest_mismatch') return 'The file changed on the way and was refused. Try again.';
  if (e.reason === 'upload_busy' || e.reason === 'offset_mismatch') return 'The hub is still receiving this upload. Try resuming it in a moment.';
  if (e.status === 409) return 'A file with this name is already here.';
  if (e.status === 413) return 'There is not enough space in this folder (quota) for this file.';
  if (e.status === 503) return 'The hub has no storage ready for files.';
  return e.message;
}

/**
 * Create the upload, send chunks, and after a dropped connection ask the hub where it got to and continue.
 * Returns the hub's sha-256 of the stored file when it sent one.
 */
export async function uploadLocalFile(
  api: Pick<OneMindApi, 'filesUploadCreate' | 'filesUploadOffset' | 'filesUploadChunk'>,
  file: LocalFile,
  root: string,
  dir: string,
  onProgress?: (sent: number, total: number) => void,
  resume?: { url?: string; created(url: string): Promise<void>; transport: TusTransport },
): Promise<{ sha256?: string }> {
  const bad = badFileName(file.name);
  if (bad) throw new ApiError(0, 'unknown', bad);
  const sha256 = !resume?.url && file.sha256 ? await file.sha256() : undefined;
  const url = resume?.url ?? await api.filesUploadCreate({ root, path: dir, name: file.name, size: file.size, sha256 });
  if (resume && !resume.url) await resume.created(url);
  async function confirmedOffset() {
    const n = await api.filesUploadOffset(url);
    if (!Number.isSafeInteger(n) || n < 0 || n > file.size) throw new ApiError(0, 'unknown', 'The upload offset exceeds the available file.');
    return n;
  }
  let offset = resume?.url ? await confirmedOffset() : 0;
  let stored: string | undefined;
  let failures = 0;
  onProgress?.(offset, file.size);
  while (offset < file.size) {
    try {
      const bytes = await file.read(offset, Math.min(CHUNK_BYTES, file.size - offset));
      if (bytes.length === 0) throw new ApiError(0, 'unknown', 'The file on this phone ended early.');
      const r = resume ? await api.filesUploadChunk(url, offset, bytes, resume.transport) : await api.filesUploadChunk(url, offset, bytes);
      if (r.offset !== offset + bytes.length || r.offset > file.size) throw new ApiError(0, 'unknown', 'The hub did not confirm this chunk.');
      offset = r.offset;
      stored = r.sha256 ?? stored;
      failures = 0;
      onProgress?.(offset, file.size);
    } catch (e) {
      const transient = e instanceof ApiError && (e.code === 'network' || e.status === 409 || e.status === 460);
      if (!transient || e.status === 409 && e.reason === 'digest_mismatch' || ++failures >= ATTEMPTS) throw e;
      offset = await confirmedOffset(); // resume from what the hub really holds
    }
  }
  if (sha256 && stored && stored.toLowerCase() !== sha256.toLowerCase()) throw new ApiError(0, 'unknown', 'The hub stored a different file than the one sent.');
  return { sha256: stored };
}
