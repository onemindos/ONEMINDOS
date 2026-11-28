<!-- SPDX-License-Identifier: Apache-2.0 -->
# OneMind Sync client kit (F1)

Plain TypeScript, no UI and no runtime dependency: a local cache, an outbox with idempotency keys,
a push/pull loop with backoff, and conflict copies. The protocol is [docs/design/SYNC.md](../../docs/design/SYNC.md).

```ts
import { SqliteStorage, SyncClient, httpTransport } from '../../clients/sync/src/index.ts';
const reminders = new SyncClient<Reminder>({
  app: 'reminders',
  storage: new SqliteStorage(await SQLite.openDatabaseAsync('onemind.db')), // expo-sqlite, once #1290 lands
  transport: httpTransport({ baseUrl: hubUrl, token: () => session.token }),
});
await reminders.save(id, { title: 'Buy milk', due_at: null, done: false }); // works offline
await reminders.syncWithBackoff();                                         // when the box is reachable
const list = await reminders.items(); // each with pending, conflictOf and ageMs
```

## Checks

The tests run with the phone app's Jest and TypeScript (no extra install); `mobile/package.json` lists this folder in `roots`.

```sh
(cd mobile && npm ci && npx jest --ci ../clients/sync)          # memory and SQLite storage
mobile/node_modules/.bin/tsc -p clients/sync/tsconfig.json     # types
```

## Against a real box: `e2e/two-devices.ts`

Needs Node 22.6 or newer and nothing else (Node runs the `.ts` files directly).

```sh
ONEMIND_HUB=https://<box>:<port> ONEMIND_TOKEN=<token> node --experimental-strip-types clients/sync/e2e/two-devices.ts
ONEMIND_HUB=... ONEMIND_TOKEN=... node --experimental-strip-types clients/sync/e2e/two-devices.ts --watch   # airplane test
```

The first run checks two devices, a conflict that keeps both copies, a replayed key and 100 queued reminders.
`--watch` makes one reminder every 3 s and tries to sync each time; switch airplane mode on and off, then
press Ctrl-C: it checks that every reminder reached the box exactly once. For a box with its own
certificate authority, fetch `/v1/tls/ca.crt` first and set `NODE_EXTRA_CA_CERTS` to that file.
