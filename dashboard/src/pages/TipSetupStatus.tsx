// SPDX-License-Identifier: Apache-2.0
import type { OneMind } from '@onemind/sdk';
import { usePoll } from '../lib/hooks';

const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};

export function TipSetupStatus({ client }: { client: OneMind }) {
  const status = usePoll(async () => {
    const read = (path: string) => client.call<unknown>({ method: 'GET', path, redirect: 'error' }).catch(() => undefined);
    const [passkeys, people, backup, kit] = await Promise.all([
      read('/v1/auth/passkeys'), read('/v1/users'), read('/v1/backups/status'), read('/v1/backups/kit'),
    ]);
    const verified = object(backup).last_verified_restore_at;
    const kitState = object(kit).state;
    return [
      { title: 'Save a passkey', done: Array.isArray(passkeys) ? passkeys.length > 0 : undefined },
      { title: 'Add another person', done: Array.isArray(people) ? people.filter((person) => object(person).disabled === false).length > 1 : undefined },
      { title: 'Verify a backup restore', done: typeof verified === 'string' ? Number.isFinite(Date.parse(verified)) : verified === null ? false : undefined },
      { title: 'Save the recovery key', done: typeof kitState === 'string' ? kitState === 'confirmed' : undefined },
    ];
  }, 0);
  if (!status.data) return <p role="status">Checking setup status…</p>;
  return <ul aria-label="Setup status">{status.data.map(({ title, done }) => <li key={title}>
    {title} <strong>{done === undefined ? 'Unknown' : done ? 'Done' : 'To do'}</strong>
  </li>)}</ul>;
}
