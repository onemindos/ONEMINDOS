// SPDX-License-Identifier: Apache-2.0
// CI-08 (#233). Two guards for the one-API-client rule:
//  1. the type contract in contract.ts really catches drift (the @ts-expect-error lines fail
//     `npm run typecheck` if it stops doing so);
//  2. no hand-written network call to /v1 sneaks in: raw fetch()/XHR only in the allowlisted
//     transport files, and every /v1 path the dashboard calls exists in the generated OpenAPI file.
import { describe, expect, it } from 'vitest';
import type { components } from '@onemind/sdk';
import type { Agrees, Expect } from './contract';

type Sdk = components['schemas'];
// @ts-expect-error a field the gateway no longer sends
type _Missing = Expect<Agrees<{ name: string; gone_field: string }, Sdk['Instance']>>;
// @ts-expect-error a field whose type changed
type _Retyped = Expect<Agrees<{ name: number }, Sdk['Instance']>>;
type _Ok = Expect<Agrees<{ name: string; version: string }, Sdk['Instance']>>;
export type Unused = [_Missing, _Retyped, _Ok];

// Every non-test source file, as text (Vite inlines these at test time; no Node typings needed).
const sources = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/*.test.ts', '!../**/*.test.tsx'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
const prod = Object.entries(sources).map(([path, text]) => ({ path: path.startsWith('./') ? `api/${path.slice(2)}` : path.replace('../', ''), text }));
const specRaw = Object.values(import.meta.glob('../../../sdk/openapi/onemind-v1.json', { query: '?raw', import: 'default', eager: true }) as Record<string, string>)[0] ?? '';

/** The only files allowed to touch the network directly; each wraps the SDK transport. */
// Files, Photos and the Backups wizard each wrap fetch with the signed-in token (a streamed or binary body the
// JSON client cannot carry). Like Backups and Migrate they are listed on purpose, so a new one is a visible choice.
// The Troubleshoot log viewer (P-07, #1125) reads the streamed text/plain journal the same way.
// The Map's asset feed passes the SDK's events.subscribe a `transport` (the SDK's own reader, with the same errors),
// only to learn when a connection ends so it can say "Reconnecting…"; the SDK still parses, resumes and backs off.
const RAW_FETCH_ALLOWED = new Set([
  'api/client.ts', 'pages/Backups.tsx', 'pages/Migrate.tsx', 'files/api.ts', 'pages/Photos.tsx', 'pages/backups/shared.ts',
  'pages/troubleshoot/LogViewer.tsx',
  'pages/map/useAssetStream.ts',
]);

describe('one API client (CI-08)', () => {
  it('has no raw fetch/XHR outside the allowlisted transport files', () => {
    const bad = prod.filter((f) => !RAW_FETCH_ALLOWED.has(f.path) && /(?<![\w.])fetch\s*\(|XMLHttpRequest|\baxios\b|globalThis\.fetch|window\.fetch/.test(f.text.replace(/\/\/.*$/gm, '')));
    expect(bad.map((f) => f.path)).toEqual([]);
  });

  it('only calls /v1 paths that exist in the generated OpenAPI file', () => {
    const spec = JSON.parse(specRaw) as { paths: Record<string, unknown> };
    const templates = Object.keys(spec.paths).map((p) => new RegExp(`^${p.replace(/[.*+?^$()|[\]\\]/g, '\\$&').replace(/\{[^}]+\}/g, '[^/]+')}$`));
    const used: Array<{ file: string; path: string }> = [];
    for (const f of prod) {
      // Path literals passed to a call: quoted or template strings that start with /v1/.
      for (const m of f.text.matchAll(/(['"`])(\/v1\/[\w\-/${}.]*)(?:\?[^'"`]*)?\1/g)) {
        const path = (m[2] as string).replace(/\$\{[^}]*\}/g, 'x');
        // Prose such as "api: '/v1/fabric, /v1/tls'" is not a call.
        if (/\sapi:\s*$/.test(f.text.slice(Math.max(0, (m.index ?? 0) - 8), m.index))) continue;
        used.push({ file: f.path, path });
      }
    }
    expect(Object.keys(spec.paths).length).toBeGreaterThan(100);
    expect(used.length).toBeGreaterThan(20);
    const unknown = used.filter((u) => !templates.some((t) => t.test(u.path)));
    expect(unknown).toEqual([]);
  });
});
