// SPDX-License-Identifier: Apache-2.0
import { File, Directory } from 'expo-file-system';
import { ApiError } from '../api/types';
import { v0Api } from '../test/fakes';
import { deliverShare, readShare } from './shareQueue';

// Emulate the Expo filesystem at its boundary. The production queue and tus loop run together.
jest.mock('expo-file-system', () => {
  const contents = new Map<string, string>();
  class Entry {
    readonly uri: string;
    readonly name: string;
    constructor(parent: string | Entry, name = '') {
      this.uri = typeof parent === 'string' ? parent : parent.uri + '/' + name;
      this.name = this.uri.split('/').pop()!;
    }
    get exists() { return contents.has(this.uri); }
    size = 1;
    write(s: string) { contents.set(this.uri, s); }
    text() { return contents.get(this.uri); }
    create() { this.write(''); }
    delete() { contents.delete(this.uri); }
    rename(name: string) { contents.set(this.uri.slice(0, this.uri.lastIndexOf('/') + 1) + name, this.text()!); this.delete(); }
  }
  return { File: Entry, Directory: Entry };
});
jest.mock('./native', () => ({ asLocalFile: (f: File, name: string) => ({ size: f.size, name, read: async () => Uint8Array.of(1) }) }));

it('checkpoints successful files, retains a refused input and retries only that file after reopening', async () => {
  const dir = new Directory('file:///queue');
  const job = { destination: { root: 'home', path: '/Inbox' }, files: ['photo.jpg', 'paper.pdf'] };
  await new File(dir, 'confirmed.json').write(JSON.stringify(job));
  const photo = new File(dir, '0'), pdf = new File(dir, '1');
  photo.create(); pdf.create();
  const create = jest.fn(async () => 'https://hub.test/upload');
  create.mockResolvedValueOnce('https://hub.test/first').mockRejectedValueOnce(new ApiError(413, 'conflict', 'quota'));
  const api = v0Api({ filesUploadCreate: create, filesUploadChunk: async () => ({ offset: 1 }) });
  const first = deliverShare(api, dir);
  expect(deliverShare(api, dir)).toBe(first);
  await expect(first).rejects.toMatchObject({ status: 413 });
  expect(photo.exists).toBe(false);
  expect(pdf.exists).toBe(true);
  expect((await readShare(dir))?.error).toMatch(/not enough space/);
  await expect(deliverShare(api, dir)).rejects.toThrow(/not enough space/);
  expect(create).toHaveBeenCalledTimes(2);
  await deliverShare(api, dir, true);
  expect(create.mock.calls).toHaveLength(3);
  expect(create).toHaveBeenLastCalledWith(expect.objectContaining({ root: 'home', path: '/Inbox', name: 'paper.pdf' }));
  expect(pdf.exists).toBe(false);
});
