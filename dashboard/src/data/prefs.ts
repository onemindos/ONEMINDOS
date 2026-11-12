// SPDX-License-Identifier: Apache-2.0
// Per-person preferences: appearance, Home layout, read notifications, recent palette commands.
// Today they live in this browser's localStorage, one slot per signed-in person (`personKey`), so
// two people sharing a browser keep their own. A hub copy is not in contract §12 (its `/v1/me/…`
// paths are not used, §12.21); `preferenceStores` switches to the ui's ApiPreferencesStore only if
// `GET /v1/instance` lists the `me.preferences` feature, which needs a contract PR first.
import {
  ApiPreferencesStore,
  LocalPreferencesStore,
  browserHomeLayoutStore,
  type HomeLayoutStore,
  type PreferencesStore,
} from '@onemind/ui';

/** PROPOSED feature name (not in §12) for a gateway that stores preferences per person. */
export const PREFERENCES_FEATURE = 'me.preferences';

/**
 * Whose slot this browser uses. Contract v0 has no "who am I" route (§12.6 adds `GET /v1/me`), so
 * against a real gateway the principal is unknown; a short fingerprint of the token then keeps
 * two people who share a browser apart. It is 32-bit FNV-1a: the token cannot be read back from
 * it, and hub tokens are 32 random bytes (deploy/install.sh, gen-tokens.sh), so it does not help
 * anyone guess one. (`crypto.subtle` is missing on a plain-HTTP v0 dashboard, hence no SHA-256.)
 */
export function personKey(principalId: string | undefined, token: string): string {
  if (principalId) return principalId;
  let h = 0x811c9dc5;
  for (let i = 0; i < token.length; i++) h = Math.imul(h ^ token.charCodeAt(i), 0x01000193) >>> 0;
  return `token-${h.toString(16).padStart(8, '0')}`;
}

function storage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** A Storage view whose keys are prefixed with the person, so preferences never mix. */
export function personStorage(personId: string, base: Storage | null = storage()): Storage | null {
  if (!base) return null;
  const k = (key: string) => `onemind.person.${personId}:${key}`;
  const view = {
    getItem: (key: string) => base.getItem(k(key)),
    setItem: (key: string, value: string) => base.setItem(k(key), value),
    removeItem: (key: string) => base.removeItem(k(key)),
    clear: () => undefined,
    key: () => null,
    length: 0,
  };
  return view as Storage;
}

export function preferenceStores(personId: string, opts: { features?: string[]; token: string }): { store: PreferencesStore; cache?: PreferencesStore } {
  const local = new LocalPreferencesStore({ storage: personStorage(personId) });
  if (opts.features?.includes(PREFERENCES_FEATURE)) return { store: new ApiPreferencesStore({ token: () => opts.token }), cache: local };
  return { store: local };
}

/** Home layout per person (the layout store already keys by person id). */
export function homeLayoutStore(): HomeLayoutStore {
  return browserHomeLayoutStore(storage() ?? undefined);
}

/** A small JSON list in the person's slot; every access guarded (private windows throw). */
export function personList(personId: string, key: string, max = 200) {
  const s = personStorage(personId);
  return {
    load(): string[] {
      try {
        const raw = s?.getItem(key);
        const v: unknown = raw ? JSON.parse(raw) : [];
        return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(-max) : [];
      } catch {
        return [];
      }
    },
    save(list: string[]) {
      try {
        s?.setItem(key, JSON.stringify(list.slice(-max)));
      } catch {
        /* storage full or blocked: works for this visit only */
      }
    },
  };
}
