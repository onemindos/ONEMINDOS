// SPDX-License-Identifier: Apache-2.0
// What the backup engine needs from the phone's photo library. The real implementation is
// expoMedia.ts (PhotoKit / MediaStore through expo-media-library); the demo and the tests use
// DemoMedia below, which makes deterministic bytes and never touches the real library.
import { sha256 } from '@noble/hashes/sha2.js';
import { bytesToHex } from '@noble/hashes/utils.js';

export type MediaPermission = 'granted' | 'limited' | 'denied' | 'undetermined';

export interface MediaAlbum {
  id: string;
  title: string;
  count: number;
}

export interface MediaAsset {
  /** Platform id (PhotoKit local identifier / MediaStore id). Never sent to the box. */
  id: string;
  fileName: string;
  kind: 'photo' | 'video';
  createdAt: number;
  modifiedAt: number;
}

export type AlbumSelection = 'all' | string[];

export interface MediaSource {
  permission(request: boolean): Promise<MediaPermission>;
  albums(): Promise<MediaAlbum[]>;
  /** Every asset in the selection, once each, oldest first. */
  list(selection: AlbumSelection): Promise<MediaAsset[]>;
  size(asset: MediaAsset): Promise<number>;
  /** `sha256:<hex>` of the exact bytes `read` returns. */
  hash(asset: MediaAsset): Promise<string>;
  read(asset: MediaAsset, offset: number, length: number): Promise<Uint8Array>;
}

export interface DemoAssetSpec {
  id: string;
  fileName: string;
  kind: 'photo' | 'video';
  size: number;
  /** Assets with the same seed have identical bytes (a duplicate on the phone). */
  seed: number;
  albums: string[];
  createdAt: number;
  modifiedAt?: number;
}

/** Deterministic pseudo-random bytes: byte i of seed s is the same on every read. */
export function demoBytes(seed: number, offset: number, length: number): Uint8Array {
  const out = new Uint8Array(length);
  for (let i = 0; i < length; i++) {
    let x = (Math.imul(seed + 1, 0x9e3779b1) ^ Math.imul(offset + i + 1, 0x85ebca6b)) >>> 0;
    x ^= x >>> 15;
    x = Math.imul(x, 0x2c1b3c6d) >>> 0;
    out[i] = (x ^ (x >>> 12)) & 0xff;
  }
  return out;
}

/** The demo makes its bytes in JavaScript; give the screen a chance to draw in between. */
const yieldToUi = () => new Promise<void>((r) => setTimeout(r, 0));

export class DemoMedia implements MediaSource {
  private readonly specs: DemoAssetSpec[];
  private readonly albumList: { id: string; title: string }[];
  private readonly hashes = new Map<number, string>();
  perm: MediaPermission;
  /** Test hook: number of `read` calls, and bytes read. */
  readonly stats = { reads: 0, bytesRead: 0, hashes: 0 };

  constructor(specs: DemoAssetSpec[], albums: { id: string; title: string }[], perm: MediaPermission = 'granted') {
    this.specs = specs;
    this.albumList = albums;
    this.perm = perm;
  }

  private spec(a: MediaAsset): DemoAssetSpec {
    const s = this.specs.find((x) => x.id === a.id);
    if (!s) throw new Error(`The file ${a.fileName} is no longer on this phone`);
    return s;
  }

  async permission(request: boolean) {
    if (request && this.perm === 'undetermined') this.perm = 'granted';
    return this.perm;
  }

  async albums() {
    return this.albumList.map((al) => ({ ...al, count: this.specs.filter((s) => s.albums.includes(al.id)).length }));
  }

  async list(selection: AlbumSelection) {
    return this.specs
      .filter((s) => selection === 'all' || s.albums.some((a) => selection.includes(a)))
      .sort((a, b) => a.createdAt - b.createdAt)
      .map((s) => ({ id: s.id, fileName: s.fileName, kind: s.kind, createdAt: s.createdAt, modifiedAt: s.modifiedAt ?? s.createdAt }));
  }

  async size(a: MediaAsset) {
    return this.spec(a).size;
  }

  async hash(a: MediaAsset) {
    const s = this.spec(a);
    this.stats.hashes++;
    const cached = this.hashes.get(s.seed * 1e9 + s.size);
    if (cached) return cached;
    const h = sha256.create();
    for (let off = 0; off < s.size; off += 1 << 20) {
      h.update(demoBytes(s.seed, off, Math.min(1 << 20, s.size - off)));
      await yieldToUi();
    }
    const v = `sha256:${bytesToHex(h.digest())}`;
    this.hashes.set(s.seed * 1e9 + s.size, v);
    return v;
  }

  async read(a: MediaAsset, offset: number, length: number) {
    const s = this.spec(a);
    const n = Math.max(0, Math.min(length, s.size - offset));
    this.stats.reads++;
    this.stats.bytesRead += n;
    await yieldToUi();
    return demoBytes(s.seed, offset, n);
  }

  /** Test hook: edit or remove an asset. */
  replace(id: string, patch: Partial<DemoAssetSpec> | null) {
    const i = this.specs.findIndex((s) => s.id === id);
    if (i < 0) return;
    if (patch === null) this.specs.splice(i, 1);
    else this.specs[i] = { ...this.specs[i]!, ...patch };
  }
}

/** The demo library shown in "Try the demo" and the screenshots: 48 items, two duplicates. */
export function demoLibrary(now = Date.now()): DemoMedia {
  const albums = [
    { id: 'camera', title: 'Camera' },
    { id: 'family', title: 'Family' },
    { id: 'trips', title: 'Trips' },
    { id: 'screens', title: 'Screenshots' },
    { id: 'receipts', title: 'Receipts' },
  ];
  const specs: DemoAssetSpec[] = [];
  const day = 86_400_000;
  for (let i = 0; i < 48; i++) {
    const video = i % 11 === 5;
    const album = i % 9 === 0 ? 'screens' : i % 7 === 0 ? 'receipts' : 'camera';
    const extra = i % 3 === 0 ? ['family'] : i % 5 === 0 ? ['trips'] : [];
    specs.push({
      id: `demo-${i}`,
      fileName: video ? `IMG_${4100 + i}.MOV` : album === 'screens' ? `Screenshot ${i}.png` : `IMG_${4100 + i}.HEIC`,
      kind: video ? 'video' : 'photo',
      size: video ? 2_500_000 + (i % 4) * 600_000 : 150_000 + ((i * 7919) % 650_000),
      // Items 20 and 21 are the same picture saved twice.
      seed: i === 21 ? 20 : i,
      albums: [album, ...extra],
      createdAt: now - (48 - i) * day,
    });
  }
  return new DemoMedia(specs, albums);
}
