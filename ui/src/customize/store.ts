// SPDX-License-Identifier: Apache-2.0
// Where appearance preferences live. The UI talks only to the PreferencesStore interface:
// - LocalPreferencesStore: this browser's localStorage. Works today; a convenience copy.
// - ApiPreferencesStore: the person's record on the hub, so every device matches.
//   PENDING CONTRACT: `GET` / `PUT /v1/me/preferences` and `PUT /v1/me/wallpaper` are not in
//   sdk/contracts/poc-v0.md yet. They are proposed as §12 (see ui/src/customize/README.md).
//   Until the gateway serves them, a 404 or 405 is reported as `pending_contract`, and the
//   provider keeps using the local copy and says so on screen.
import { normalizePreferences, type AppearancePreferences } from './preferences';

export interface StoredPreferences {
  prefs: AppearancePreferences;
  /** RFC 3339 time of the last save, or null when nothing was ever saved (defaults). */
  updatedAt: string | null;
}

export type PreferencesErrorCode =
  | 'storage_unavailable'
  | 'quota_exceeded'
  | 'unauthenticated'
  | 'permission_denied'
  | 'pending_contract'
  | 'network'
  | 'invalid_response';

export class PreferencesError extends Error {
  readonly code: PreferencesErrorCode;
  constructor(code: PreferencesErrorCode, message: string) {
    super(message);
    this.name = 'PreferencesError';
    this.code = code;
  }
}

export interface PreferencesStore {
  /** `local` = this browser only; `hub` = the person's record on the box. */
  readonly kind: 'local' | 'hub';
  load(): Promise<StoredPreferences>;
  save(prefs: AppearancePreferences): Promise<StoredPreferences>;
  /** An uploaded wallpaper as a data URL, or null. */
  loadWallpaperImage(): Promise<string | null>;
  saveWallpaperImage(dataUrl: string | null): Promise<void>;
}

export const LOCAL_SLOT = 'onemind.appearance.v1';
export const LOCAL_IMAGE_SLOT = 'onemind.appearance.wallpaper';

function defaultStorage(): Storage | null {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** localStorage adapter. Every access is guarded: private windows and blocked storage throw. */
export class LocalPreferencesStore implements PreferencesStore {
  readonly kind = 'local' as const;
  private readonly storage: Storage | null;
  private readonly clock: () => Date;

  constructor(opts: { storage?: Storage | null; clock?: () => Date } = {}) {
    this.storage = opts.storage === undefined ? defaultStorage() : opts.storage;
    this.clock = opts.clock ?? (() => new Date());
  }

  private get s(): Storage {
    if (!this.storage) throw new PreferencesError('storage_unavailable', 'This browser does not allow saving settings.');
    return this.storage;
  }

  async load(): Promise<StoredPreferences> {
    let raw: string | null;
    try {
      raw = this.s.getItem(LOCAL_SLOT);
    } catch (e) {
      throw e instanceof PreferencesError ? e : new PreferencesError('storage_unavailable', 'This browser does not allow reading saved settings.');
    }
    if (!raw) return { prefs: normalizePreferences(null), updatedAt: null };
    try {
      const doc = JSON.parse(raw) as { appearance?: unknown; updated_at?: unknown };
      return { prefs: normalizePreferences(doc.appearance), updatedAt: typeof doc.updated_at === 'string' ? doc.updated_at : null };
    } catch {
      return { prefs: normalizePreferences(null), updatedAt: null };
    }
  }

  async save(prefs: AppearancePreferences): Promise<StoredPreferences> {
    const updatedAt = this.clock().toISOString();
    try {
      this.s.setItem(LOCAL_SLOT, JSON.stringify({ appearance: prefs, updated_at: updatedAt }));
    } catch (e) {
      throw toStorageError(e);
    }
    return { prefs, updatedAt };
  }

  async loadWallpaperImage(): Promise<string | null> {
    try {
      return this.s.getItem(LOCAL_IMAGE_SLOT);
    } catch {
      return null;
    }
  }

  async saveWallpaperImage(dataUrl: string | null): Promise<void> {
    try {
      if (dataUrl === null) this.s.removeItem(LOCAL_IMAGE_SLOT);
      else this.s.setItem(LOCAL_IMAGE_SLOT, dataUrl);
    } catch (e) {
      throw toStorageError(e);
    }
  }
}

function toStorageError(e: unknown): PreferencesError {
  if (e instanceof PreferencesError) return e;
  const name = (e as { name?: string } | null)?.name ?? '';
  if (name === 'QuotaExceededError' || name === 'NS_ERROR_DOM_QUOTA_REACHED') {
    return new PreferencesError('quota_exceeded', 'Not enough room in this browser to keep it.');
  }
  return new PreferencesError('storage_unavailable', 'This browser does not allow saving settings.');
}

/** Path of the proposed endpoint. */
export const PREFERENCES_PATH = '/v1/me/preferences';
export const WALLPAPER_PATH = '/v1/me/wallpaper';
export const API_CONTRACT_STATUS = 'pending: proposed as contract §12, not served by the gateway yet';

export interface ApiStoreOptions {
  /** Gateway origin; '' means same origin (the dashboard is served by the gateway, §3). */
  baseUrl?: string;
  /** Returns the bearer token of the signed-in person (§3 auth). */
  token?: () => string | null;
  fetch?: typeof fetch;
}

/**
 * Hub adapter for the proposed §12 endpoints. Request and response bodies:
 * `{"appearance": AppearancePreferences, "updated_at": "RFC3339"}`. A person can read and write
 * only their own record; an agent principal gets 403 (appearance is personal, never an agent scope).
 */
export class ApiPreferencesStore implements PreferencesStore {
  readonly kind = 'hub' as const;
  private readonly base: string;
  private readonly token: () => string | null;
  private readonly f: typeof fetch;

  constructor(opts: ApiStoreOptions = {}) {
    this.base = (opts.baseUrl ?? '').replace(/\/$/, '');
    this.token = opts.token ?? (() => null);
    this.f = opts.fetch ?? ((...a) => globalThis.fetch(...a));
  }

  private headers(json: boolean): HeadersInit {
    const h: Record<string, string> = { accept: 'application/json' };
    if (json) h['content-type'] = 'application/json';
    const t = this.token();
    if (t) h.authorization = `Bearer ${t}`;
    return h;
  }

  private async call(path: string, init: RequestInit): Promise<Response> {
    let res: Response;
    try {
      res = await this.f(`${this.base}${path}`, init);
    } catch {
      throw new PreferencesError('network', 'The hub could not be reached.');
    }
    if (res.ok) return res;
    if (res.status === 401) throw new PreferencesError('unauthenticated', 'Sign in again to load your settings.');
    if (res.status === 403) throw new PreferencesError('permission_denied', 'Only the person can change their own appearance.');
    if (res.status === 404 || res.status === 405 || res.status === 501) {
      throw new PreferencesError('pending_contract', 'The hub does not store appearance yet (contract §12 pending).');
    }
    throw new PreferencesError('network', `The hub answered ${res.status}.`);
  }

  private async parse(res: Response): Promise<StoredPreferences> {
    try {
      const body = (await res.json()) as { appearance?: unknown; updated_at?: unknown };
      if (!body || typeof body !== 'object' || !('appearance' in body)) throw new Error('shape');
      return { prefs: normalizePreferences(body.appearance), updatedAt: typeof body.updated_at === 'string' ? body.updated_at : null };
    } catch {
      throw new PreferencesError('invalid_response', 'The hub sent settings this version cannot read.');
    }
  }

  async load(): Promise<StoredPreferences> {
    return this.parse(await this.call(PREFERENCES_PATH, { method: 'GET', headers: this.headers(false) }));
  }

  async save(prefs: AppearancePreferences): Promise<StoredPreferences> {
    const res = await this.call(PREFERENCES_PATH, { method: 'PUT', headers: this.headers(true), body: JSON.stringify({ appearance: prefs }) });
    return this.parse(res);
  }

  async loadWallpaperImage(): Promise<string | null> {
    const res = await this.call(WALLPAPER_PATH, { method: 'GET', headers: this.headers(false) });
    const body = (await res.json().catch(() => null)) as { data_url?: unknown } | null;
    return typeof body?.data_url === 'string' ? body.data_url : null;
  }

  async saveWallpaperImage(dataUrl: string | null): Promise<void> {
    await this.call(WALLPAPER_PATH, dataUrl === null ? { method: 'DELETE', headers: this.headers(false) } : { method: 'PUT', headers: this.headers(true), body: JSON.stringify({ data_url: dataUrl }) });
  }
}

/** A store that never answers (demo and tests of the loading state). */
export class PendingStore implements PreferencesStore {
  readonly kind = 'hub' as const;
  load = () => new Promise<StoredPreferences>(() => {});
  save = (prefs: AppearancePreferences) => Promise.resolve({ prefs, updatedAt: null });
  loadWallpaperImage = () => Promise.resolve(null);
  saveWallpaperImage = () => Promise.resolve();
}
