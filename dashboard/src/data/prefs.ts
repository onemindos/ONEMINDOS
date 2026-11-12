// SPDX-License-Identifier: Apache-2.0
// Per-person preferences: appearance, Home layout, read notifications, recent palette commands.
// Today they live in this browser's localStorage, one slot per signed-in principal, so two people
// sharing a browser keep their own. The hub copy (§12, `GET/PUT /v1/me/preferences`) is not on
// main yet: `preferenceStores` switches to it once `GET /v1/instance` lists the feature
// (§12.1 `features`), keeping the browser copy as the fallback cache.
import {
  ApiPreferencesStore,
  LocalPreferencesStore,
  browserHomeLayoutStore,
  type HomeLayoutStore,
  type PreferencesStore,
} from '@onemind/ui';

/** The §12.1 feature name the gateway will list when it stores preferences per person. */
export const PREFERENCES_FEATURE = 'me.preferences';

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
