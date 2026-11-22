// SPDX-License-Identifier: Apache-2.0
// The name Home greets: the signed-in person's display_name from GET /v1/me. The field is
// optional, so a missing or empty one (or a failed call) gives no name and the greeting stays
// "Good afternoon"; nothing here invents a name from an id or a role.
import { greetingName } from '@onemind/ui';
import type { Me } from '../api/wiring';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';

/** The first name to greet, from the /v1/me answer; undefined when there is none worth saying. */
export function displayNameOf(me: Me | { display_name?: unknown; principal?: { kind?: string; display_name?: unknown } } | null | undefined): string | undefined {
  if (!me || typeof me !== 'object') return undefined;
  const top = (me as { display_name?: unknown }).display_name;
  const inner = (me as { principal?: { kind?: string; display_name?: unknown } }).principal;
  if (inner && inner.kind !== undefined && inner.kind !== 'person') return undefined;
  const raw = typeof top === 'string' && top.trim() ? top : inner?.display_name;
  return typeof raw === 'string' ? greetingName(raw) : undefined;
}

export function useDisplayName(): string | undefined {
  const { api } = useSignedIn();
  const me = usePoll(async () => {
    try {
      return await api.me();
    } catch {
      return null;
    }
  }, 0);
  return displayNameOf(me.data);
}
