// SPDX-License-Identifier: Apache-2.0
// Files download request and tus upload calls (docs/leap/core/FILES.md section 3), and the chunk loop on top.
import { HttpApi, OP, type FetchLike } from './client';
import { ApiError } from './types';
import { CHUNK_BYTES, badFileName, uploadLocalFile, uploadProblem, type LocalFile } from '../lib/filesTransfer';

type Call = { url: string; init: RequestInit };
const unb64 = (v: string) => new TextDecoder().decode(Uint8Array.from(atob(v), (c) => c.charCodeAt(0)));
const hdr = (c: Call, k: string) => (c.init.headers as Record<string, string>)[k];

function hub(answer: (c: Call) => Response) {
  const calls: Call[] = [];
  const fetchFn: FetchLike = async (url, init) => {
    const c = { url, init: init ?? {} };
    calls.push(c);
    return answer(c);
  };
  return { api: new HttpApi({ baseUrl: 'https://hub.test', token: 't', fetchFn }), calls };
}

describe('files download and tus calls', () => {
  it('builds a download request with the bearer and an encoded path', () => {
    const r = hub(() => new Response('{}'));
    expect(r.api.filesDownloadRequest('home:alex', '/a b/c&d.txt')).toEqual({
      url: 'https://hub.test/v1/files/download?root=home%3Aalex&path=%2Fa%20b%2Fc%26d.txt',
      headers: { 'OneMind-API-Version': '1', Authorization: 'Bearer t' },
    });
  });

  it('creates an upload with base64 tus metadata and returns an absolute address', async () => {
    const r = hub(() => new Response(null, { status: 201, headers: { Location: '/v1/files/uploads/upl_1' } }));
    const url = await r.api.filesUploadCreate({ root: 'shared', path: '/Docs', name: 'späß.txt', size: 5, sha256: 'ab' });
    expect(url).toBe('https://hub.test/v1/files/uploads/upl_1');
    const c = r.calls[0]!;
    expect(c.init.method).toBe('POST');
    expect(hdr(c, 'Tus-Resumable')).toBe('1.0.0');
    expect(hdr(c, 'Upload-Length')).toBe('5');
    expect(hdr(c, 'Authorization')).toBe('Bearer t');
    const meta = Object.fromEntries(hdr(c, 'Upload-Metadata')!.split(',').map((p) => p.split(' ') as [string, string]));
    expect(unb64(meta.filename!)).toBe('späß.txt');
    expect(unb64(meta.root!)).toBe('shared');
    expect(unb64(meta.path!)).toBe('/Docs');
    expect(unb64(meta.sha256!)).toBe('ab');
  });

  it('refuses an upload address on another origin (the token must not leave the hub)', async () => {
    const r = hub(() => new Response(null, { status: 204, headers: { 'Upload-Offset': '0' } }));
    await expect(r.api.filesUploadOffset('https://evil.test/v1/files/uploads/x')).rejects.toBeInstanceOf(ApiError);
    expect(r.calls).toHaveLength(0);
  });

  it('PATCHes a chunk and reads the offset and the stored sha256', async () => {
    const r = hub(() => new Response(null, { status: 204, headers: { 'Upload-Offset': '3', 'OneMind-File-Sha256': 'abc' } }));
    const out = await r.api.filesUploadChunk('https://hub.test/v1/files/uploads/u', 0, new Uint8Array([1, 2, 3]));
    expect(out).toEqual({ offset: 3, sha256: 'abc' });
    expect(hdr(r.calls[0]!, 'Content-Type')).toBe('application/offset+octet-stream');
    expect(hdr(r.calls[0]!, 'Upload-Offset')).toBe('0');
  });

  it('turns a 413 quota answer into a typed error', async () => {
    const r = hub(() => new Response(JSON.stringify({ error: 'conflict', message: 'quota', reason: 'quota_exceeded' }), { status: 413 }));
    const e = (await r.api.filesUploadCreate({ root: 'r', path: '/', name: 'x', size: 1 }).catch((x: unknown) => x)) as ApiError;
    expect(e.status).toBe(413);
    expect(uploadProblem(e)).toMatch(/quota/);
  });

  it('files routes are feature-detectable', () => {
    for (const op of [OP.filesDownload, OP.filesUploads]) expect(op).toMatch(/^(GET|POST) \/v1\/files\//);
  });
});

function fakeFile(size: number, over: Partial<LocalFile> = {}): LocalFile {
  return { name: 'a.bin', size, read: async (o, n) => new Uint8Array(n).fill(o % 251), ...over };
}

describe('uploadLocalFile', () => {
  it('sends in chunks and reports progress', async () => {
    const chunks: number[] = [];
    const api = {
      filesUploadCreate: jest.fn(async () => 'https://hub.test/u'),
      filesUploadOffset: jest.fn(async () => 0),
      filesUploadChunk: jest.fn(async (_u: string, o: number, b: Uint8Array) => {
        chunks.push(o);
        return { offset: o + b.length };
      }),
    };
    const seen: number[] = [];
    await uploadLocalFile(api, fakeFile(CHUNK_BYTES * 2 + 10), 'shared', '/Docs', (s) => seen.push(s));
    expect(chunks).toEqual([0, CHUNK_BYTES, CHUNK_BYTES * 2]);
    expect(seen.at(-1)).toBe(CHUNK_BYTES * 2 + 10);
    expect(api.filesUploadCreate).toHaveBeenCalledWith({ root: 'shared', path: '/Docs', name: 'a.bin', size: CHUNK_BYTES * 2 + 10, sha256: undefined });
  });

  it('resumes from the hub offset after a dropped connection', async () => {
    let n = 0;
    const api = {
      filesUploadCreate: async () => 'https://hub.test/u',
      filesUploadOffset: jest.fn(async () => 0),
      filesUploadChunk: jest.fn(async (_u: string, o: number, b: Uint8Array) => {
        if (n++ === 0) throw new ApiError(0, 'network', 'dropped');
        return { offset: o + b.length };
      }),
    };
    await uploadLocalFile(api, fakeFile(100), 'r', '/');
    expect(api.filesUploadOffset).toHaveBeenCalledTimes(1);
    expect(api.filesUploadChunk).toHaveBeenCalledTimes(2);
  });

  it('does not retry a permission refusal, and gives up after repeated drops', async () => {
    const denied = { filesUploadCreate: async () => 'u', filesUploadOffset: async () => 0, filesUploadChunk: async () => { throw new ApiError(403, 'permission_denied', 'no'); } };
    await expect(uploadLocalFile(denied, fakeFile(10), 'r', '/')).rejects.toMatchObject({ status: 403 });
    const flaky = { filesUploadCreate: async () => 'u', filesUploadOffset: jest.fn(async () => 0), filesUploadChunk: async () => { throw new ApiError(0, 'network', 'x'); } };
    await expect(uploadLocalFile(flaky, fakeFile(10), 'r', '/')).rejects.toMatchObject({ code: 'network' });
    expect(flaky.filesUploadOffset).toHaveBeenCalledTimes(3);
  });

  it('fails when the hub stored a different hash than the phone computed', async () => {
    const api = {
      filesUploadCreate: async () => 'u',
      filesUploadOffset: async () => 0,
      filesUploadChunk: async (_u: string, o: number, b: Uint8Array) => ({ offset: o + b.length, sha256: 'bb' }),
    };
    await expect(uploadLocalFile(api, fakeFile(4, { sha256: async () => 'aa' }), 'r', '/')).rejects.toThrow(/different file/);
  });

  it('refuses names with slashes before sending anything', async () => {
    expect(badFileName('a/b')).toBeTruthy();
    expect(badFileName('ok.txt')).toBeUndefined();
    const api = { filesUploadCreate: jest.fn(), filesUploadOffset: jest.fn(), filesUploadChunk: jest.fn() };
    await expect(uploadLocalFile(api, fakeFile(1, { name: '../x' }), 'r', '/')).rejects.toBeInstanceOf(ApiError);
    expect(api.filesUploadCreate).not.toHaveBeenCalled();
  });
});
