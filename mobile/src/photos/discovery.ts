// SPDX-License-Identifier: Apache-2.0
// Finds the box's Photos service through the OneMind catalog (`GET /v1/apps`, contract §3).
// The photos study (§4.1, decision C) makes Photos a first-party app with id `photos`; the
// gateway serves its API under the hub's own origin at /v1/photos/... (interim, §12-p pending).
import type { CatalogApp } from '../api/types';
import type { Connection } from '../storage';

export const PHOTOS_APP_ID = 'photos';

export type Availability =
  | { state: 'ok'; baseUrl: string; demo: boolean }
  | { state: 'checking' }
  | { state: 'not_in_catalog' }
  | { state: 'not_installed' }
  | { state: 'not_running'; status: string }
  | { state: 'needs_https'; hubUrl: string };

/** App statuses that mean the service can take requests. */
const UP = new Set(['running', 'installed', 'healthy']);

export function discoverPhotos(conn: Connection, apps: CatalogApp[] | undefined, demoOrigin: string): Availability {
  if (conn.mode === 'mock') return { state: 'ok', baseUrl: demoOrigin, demo: true };
  if (!apps) return { state: 'checking' };
  const app = apps.find((a) => a.id === PHOTOS_APP_ID);
  if (!app) return { state: 'not_in_catalog' };
  if (!app.installed) return { state: 'not_installed' };
  if (!UP.has(app.status)) return { state: 'not_running', status: app.status };
  // B3 / DN-1: never plain HTTP for photos, even on the home network.
  if (!conn.hubUrl.startsWith('https://')) return { state: 'needs_https', hubUrl: conn.hubUrl };
  return { state: 'ok', baseUrl: conn.hubUrl, demo: false };
}
