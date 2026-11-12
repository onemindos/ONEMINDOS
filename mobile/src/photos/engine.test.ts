// SPDX-License-Identifier: Apache-2.0
// The backup engine against the in-memory box: dedupe, resume, rules and selection.
import { blockReason, runBackup, type Conditions, type RunDeps } from './engine';
import { counts, MemoryStore, type BackupSettings } from './ledger';
import { DemoMedia, type DemoAssetSpec } from './media';
import { MockPhotosServer } from './mockServer';
import { HttpPhotosApi } from './protocol';

const KB = 1024;

function spec(i: number, size: number, extra: Partial<DemoAssetSpec> = {}): DemoAssetSpec {
  return { id: `a${i}`, fileName: `IMG_${i}.HEIC`, kind: 'photo', size, seed: i, albums: ['camera'], createdAt: 1000 + i, ...extra };
}

function setup(specs: DemoAssetSpec[], opts: { settings?: Partial<BackupSettings>; conditions?: Conditions } = {}) {
  const server = new MockPhotosServer({ token: 'tok' });
  const api = new HttpPhotosApi({ baseUrl: server.origin, token: 'tok', fetchFn: server.fetch });
  const media = new DemoMedia(specs, [
    { id: 'camera', title: 'Camera' },
    { id: 'family', title: 'Family' },
  ]);
  const store = new MemoryStore();
  let cond: Conditions = opts.conditions ?? { network: 'wifi', power: 'battery' };
  const settings: BackupSettings = { enabled: true, wifiOnly: true, chargingOnly: false, albums: 'all', ...opts.settings };
  const deps = (more: Partial<RunDeps> = {}): RunDeps => ({
    api,
    media,
    store,
    settings,
    conditions: async () => cond,
    platform: 'ios',
    deviceName: 'Test phone',
    trigger: 'manual',
    chunkSize: 64 * KB,
    saveEveryMs: 0,
    ...more,
  });
  return { server, api, media, store, deps, setCond: (c: Conditions) => (cond = c) };
}

describe('backup engine', () => {
  it('uploads every selected item once and records receipts', async () => {
    const t = setup([spec(1, 100 * KB), spec(2, 300 * KB), spec(3, 1 * KB)]);
    const r = await runBackup(t.deps());
    expect(r.outcome).toBe('completed');
    expect(r.uploaded).toBe(3);
    expect(t.server.stats.bytesReceived).toBe(401 * KB);
    expect(t.server.stats.uploadsCompleted).toBe(3);
    const l = await t.store.loadLedger();
    expect(counts(l)).toEqual({ total: 3, done: 3, waiting: 0, failed: 0 });
    expect(l!.lastComplete).toBeDefined();
    expect(l!.coverage?.on_box).toBe(3);
  });

  it('dedupes by hash: identical bytes on the phone are sent once', async () => {
    const t = setup([spec(1, 200 * KB), spec(2, 200 * KB, { seed: 1, fileName: 'copy.HEIC' })]);
    const r = await runBackup(t.deps());
    expect(r.outcome).toBe('completed');
    expect(r.uploaded).toBe(1);
    expect(r.deduped).toBe(1);
    expect(t.server.stats.bytesReceived).toBe(200 * KB);
    expect(t.server.stats.storedBlobs).toBe(1);
  });

  it('a second run uploads nothing and does not rehash unchanged items', async () => {
    const t = setup([spec(1, 50 * KB), spec(2, 70 * KB)]);
    await runBackup(t.deps());
    const hashes = t.media.stats.hashes;
    const before = t.server.stats.bytesReceived;
    const r = await runBackup(t.deps());
    expect(r.uploaded + r.deduped).toBe(0);
    expect(t.server.stats.bytesReceived).toBe(before);
    expect(t.media.stats.hashes).toBe(hashes);
  });

  it('after the phone loses its ledger (reinstall) the box answers "have" and nothing is re-sent', async () => {
    const t = setup([spec(1, 50 * KB)]);
    await runBackup(t.deps());
    const ledger = await t.store.loadLedger();
    // Simulate a lost item record but the same install id and source (e.g. a corrupt entry).
    ledger!.items = {};
    await t.store.saveLedger(ledger!);
    const before = t.server.stats.bytesReceived;
    const r = await runBackup(t.deps());
    expect(r.deduped).toBe(1);
    expect(t.server.stats.bytesReceived).toBe(before);
  });

  it('resumes a dropped upload from the box offset instead of restarting', async () => {
    const t = setup([spec(1, 640 * KB)]);
    t.server.faults.cutNextPatchAfter = undefined;
    // Let three chunks through, then drop the connection half-way into the fourth.
    let patches = 0;
    const orig = t.server.fetch;
    const api = new HttpPhotosApi({
      baseUrl: t.server.origin,
      token: 'tok',
      fetchFn: async (u, i) => {
        if (i?.method === 'PATCH' && ++patches === 4) t.server.faults.cutNextPatchAfter = 10 * KB;
        return orig(u, i);
      },
    });
    const r1 = await runBackup(t.deps({ api }));
    expect(r1.outcome).toBe('stopped');
    expect(r1.reason).toBe('connection_lost');
    expect(t.server.stats.bytesReceived).toBe(3 * 64 * KB + 10 * KB);

    const r2 = await runBackup(t.deps({ api }));
    expect(r2.outcome).toBe('completed');
    expect(r2.uploaded).toBe(1);
    // Every byte crossed the wire exactly once, across both runs.
    expect(t.server.stats.bytesReceived).toBe(640 * KB);
    expect(t.server.stats.uploadsCreated).toBe(1);
  });

  it('survives three disconnects in one large upload and ends with one stored copy', async () => {
    const t = setup([spec(1, 1024 * KB)]);
    for (let i = 0; i < 3; i++) {
      t.server.faults.failPatches = 1;
      const r = await runBackup(t.deps());
      expect(r.outcome).toBe('stopped');
      // Let a few chunks through before the next drop.
      t.server.faults.cutNextPatchAfter = 5 * KB;
      await runBackup(t.deps());
    }
    const r = await runBackup(t.deps());
    expect(r.outcome).toBe('completed');
    expect(t.server.stats.storedBlobs).toBe(1);
    expect(t.server.stats.bytesReceived).toBe(1024 * KB);
  });

  it('Wi-Fi only: on mobile data nothing is sent and the run says why', async () => {
    const t = setup([spec(1, 10 * KB)], { conditions: { network: 'cellular', power: 'charging' } });
    const r = await runBackup(t.deps());
    expect(r).toMatchObject({ outcome: 'blocked', reason: 'needs_wifi' });
    expect(t.server.stats.patches).toBe(0);
  });

  it('stops between chunks when Wi-Fi is lost, then continues on Wi-Fi', async () => {
    const t = setup([spec(1, 256 * KB)]);
    let n = 0;
    const r1 = await runBackup(
      t.deps({
        onProgress: (p) => {
          if (p.phase === 'uploading' && p.current && p.current.sent > 0 && ++n === 1) t.setCond({ network: 'cellular', power: 'battery' });
        },
      }),
    );
    expect(r1).toMatchObject({ outcome: 'blocked', reason: 'needs_wifi' });
    expect(t.server.stats.bytesReceived).toBe(64 * KB);
    t.setCond({ network: 'wifi', power: 'battery' });
    expect((await runBackup(t.deps())).outcome).toBe('completed');
    expect(t.server.stats.bytesReceived).toBe(256 * KB);
  });

  it('charging only: waits for power', async () => {
    const t = setup([spec(1, 10 * KB)], { settings: { chargingOnly: true }, conditions: { network: 'wifi', power: 'battery' } });
    expect(await runBackup(t.deps())).toMatchObject({ outcome: 'blocked', reason: 'needs_charging' });
  });

  it('with Wi-Fi only off, mobile data is allowed', () => {
    const s: BackupSettings = { enabled: true, wifiOnly: false, chargingOnly: false, albums: 'all' };
    expect(blockReason(s, { network: 'cellular', power: 'battery' })).toBeUndefined();
    expect(blockReason(s, { network: 'none', power: 'battery' })).toBe('offline');
    expect(blockReason({ ...s, enabled: false }, { network: 'wifi', power: 'charging' })).toBe('disabled');
  });

  it('backs up only the chosen albums', async () => {
    const t = setup([spec(1, 10 * KB), spec(2, 10 * KB, { albums: ['family'] }), spec(3, 10 * KB, { albums: ['camera', 'family'] })], {
      settings: { albums: ['family'] },
    });
    const r = await runBackup(t.deps());
    expect(r.uploaded).toBe(2);
    expect(counts(await t.store.loadLedger()).total).toBe(2);
  });

  it('stops at the deadline and continues next time', async () => {
    const t = setup([spec(1, 10 * KB), spec(2, 10 * KB)]);
    let clock = 0;
    const r1 = await runBackup(t.deps({ now: () => clock++, deadline: 0 }));
    expect(r1).toMatchObject({ outcome: 'stopped', reason: 'time_up' });
    expect((await runBackup(t.deps())).outcome).toBe('completed');
  });

  it('an edited photo is sent again; a file that cannot be read is marked and skipped', async () => {
    const t = setup([spec(1, 10 * KB), spec(2, 10 * KB)]);
    await runBackup(t.deps());
    t.media.replace('a1', { seed: 99, modifiedAt: 5000 });
    t.media.replace('a2', { size: 20 * KB, seed: 98, modifiedAt: 6000 });
    t.media.size = async (a) => (a.id === 'a2' ? Promise.reject(new Error('File unavailable (iCloud only)')) : 10 * KB);
    const r = await runBackup(t.deps());
    expect(r.uploaded).toBe(1);
    const l = await t.store.loadLedger();
    expect(counts(l)).toMatchObject({ done: 1, failed: 1 });
    expect(l!.items.a2!.error).toMatch(/iCloud/);
  });

  it('two phones of different people never learn of each other’s photos', async () => {
    const t = setup([spec(1, 10 * KB)]);
    await runBackup(t.deps());
    // A second phone with the same bytes: its own source, so the box asks for the upload.
    const other = new MemoryStore();
    const r = await runBackup({ ...t.deps(), store: other, deviceName: 'Other phone' });
    expect(r.uploaded).toBe(1);
    expect(r.deduped).toBe(0);
  });

  it('refuses plain HTTP before anything is sent', () => {
    expect(() => new HttpPhotosApi({ baseUrl: 'http://box.local:8080', token: 't' })).toThrow(/HTTPS/);
  });
});
