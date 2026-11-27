// SPDX-License-Identifier: Apache-2.0
// The kit against a REAL gateway: two "devices" (two caches and outboxes) of one person.
//   ONEMIND_HUB=https://<box>:<port> ONEMIND_TOKEN=<your token> node --experimental-strip-types clients/sync/e2e/two-devices.ts
// Add --watch to create a reminder every 3 s while you switch airplane mode on and off (Ctrl-C stops and checks).
import { MemoryStorage, SyncClient, httpTransport, type ItemView } from '../src/index.ts';

type Reminder = { title: string; due_at?: string | null; done?: boolean };
const hub = process.env.ONEMIND_HUB;
const token = process.env.ONEMIND_TOKEN;
if (!hub || !token) throw new Error('set ONEMIND_HUB and ONEMIND_TOKEN');
const transport = httpTransport<Reminder>({ baseUrl: hub.replace(/\/$/, ''), token: () => token });
const device = () => new SyncClient<Reminder>({ app: 'reminders', storage: new MemoryStorage(), transport,
  backoff: { baseMs: 1000, maxMs: 30_000, attempts: 1_000 } });
const run = Date.now().toString(36);
let failed = 0;
const check = (ok: boolean, what: string) => { console.log(`${ok ? 'PASS' : 'FAIL'} ${what}`); if (!ok) failed += 1; };
const timed = async <T>(what: string, f: () => Promise<T>) => {
  const t0 = performance.now(); const out = await f(); console.log(`  ${what}: ${(performance.now() - t0).toFixed(0)} ms`); return out;
};
const mine = (items: ItemView<Reminder>[]) => items.filter((i) => i.id.startsWith(run)).map((i) => i.data?.title).sort();

async function scripted() {
  const phone = device();
  const laptop = device();
  await phone.save(`${run}-a`, { title: 'Buy milk', due_at: new Date(Date.now() + 86_400_000).toISOString() });
  await timed('phone first sync (whole feed)', () => phone.sync());
  await timed('laptop first sync (whole feed)', () => laptop.sync());
  check(mine(await laptop.items()).includes('Buy milk'), 'the laptop sees the phone\'s reminder');
  await phone.save(`${run}-a`, { title: 'Buy oat milk' }); // both edit, neither has synced
  await laptop.save(`${run}-a`, { title: 'Buy milk and eggs' });
  await phone.sync();
  check((await laptop.sync()).conflicts === 1, 'the second edit is a conflict');
  await phone.sync();
  for (const [n, d] of [['phone', phone], ['laptop', laptop]] as const) {
    check(JSON.stringify(mine(await d.items())) === JSON.stringify(['Buy milk and eggs', 'Buy oat milk']), `${n} keeps both copies`);
  }
  const op = { key: `${run}-replay`, item_id: `${run}-b`, op: 'upsert' as const, base_version: null, data: { title: 'Once' } };
  const [first] = await transport.push('reminders', [op]);
  const [again] = await transport.push('reminders', [op]);
  check(first?.replayed === false && again?.replayed === true && again.version === 1, 'a replayed key is answered, not applied');
  await phone.sync();
  check(mine(await phone.items()).filter((t) => t === 'Once').length === 1, 'the replayed reminder exists once');
  const many = device();
  for (let i = 0; i < 100; i += 1) await many.save(`${run}-m${i}`, { title: `Bulk ${i}` });
  await timed('push 100 queued reminders + pull', () => many.sync());
  check((await many.pending()) === 0, '100 queued reminders all sent');
}

async function watch() {
  const phone = device();
  let made = 0;
  let stop = false;
  process.on('SIGINT', () => { stop = true; });
  while (!stop) {
    await phone.save(`${run}-w${made}`, { title: `Watch ${made}` });
    made += 1;
    try { // one try per tick: offline, the outbox grows; back online, one sync sends it all
      const r = await phone.sync();
      console.log(`made ${made}, waiting ${await phone.pending()}, sent ${r.pushed}`);
    } catch (e) { console.log(`made ${made}, waiting ${await phone.pending()}: ${(e as Error).message}`); }
    await new Promise((r) => setTimeout(r, 3000));
  }
  await phone.syncWithBackoff();
  const fresh = device();
  await fresh.sync();
  const onBox = mine(await fresh.items()).length;
  check(onBox === made && (await phone.pending()) === 0, `${made} made, ${onBox} on the box: each exactly once`);
}

await (process.argv.includes('--watch') ? watch() : scripted());
process.exit(failed ? 1 : 0);
