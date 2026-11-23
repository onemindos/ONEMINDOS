// SPDX-License-Identifier: Apache-2.0
// Guard (wave P, phone-no-demo): no screen a person can reach runs on made-up data. The in-memory gateway
// (api/mock.ts), its fixtures (api/fixtures.ts), the in-memory Photos box (photos/mockServer.ts) and the
// made-up photo library stay in tests. This fails as soon as any app file imports them again.

// No @types/node in this package: the few Node pieces used are typed here (as in nodeFetch.ts).
declare const __dirname: string;
interface Entry {
  name: string;
  isDirectory(): boolean;
}
const fs = jest.requireActual<{
  readdirSync(dir: string, opts: { withFileTypes: true }): Entry[];
  readFileSync(file: string, enc: 'utf8'): string;
  existsSync(file: string): boolean;
}>('fs');
const path = jest.requireActual<{
  resolve(...parts: string[]): string;
  join(...parts: string[]): string;
  relative(from: string, to: string): string;
  dirname(p: string): string;
  sep: string;
}>('path');

const MOBILE = path.resolve(__dirname, '..', '..');
const SRC = path.join(MOBILE, 'src');

/** Modules only tests may load (without extension). */
const TEST_ONLY = ['src/api/mock', 'src/api/fixtures', 'src/photos/mockServer'].map((m) => path.join(MOBILE, m));

/** Names only tests may use, with the one file allowed to define each. */
const TEST_ONLY_NAMES: Record<string, string[]> = {
  demoLibrary: [],
  MockApi: ['src/api/mock.ts'],
  MockPhotosServer: ['src/photos/mockServer.ts'],
  DEMO_TOKENS: ['src/api/fixtures.ts', 'src/api/mock.ts'],
  DemoMedia: ['src/photos/media.ts'],
};

const isTest = (f: string) => /\.test\.tsx?$/.test(f) || f.startsWith(path.join(SRC, 'test') + path.sep);

function walk(dir: string, out: string[] = []): string[] {
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else if (/\.(ts|tsx|js|jsx)$/.test(e.name)) out.push(p);
  }
  return out;
}

/** App files: the entry points plus everything under src/ that is not a test, a test helper or a test-only module. */
function runtimeFiles(): string[] {
  const entries = ['App.tsx', 'index.ts'].map((f) => path.join(MOBILE, f)).filter((f) => fs.existsSync(f));
  const testOnly = (f: string) => TEST_ONLY.includes(f.replace(/\.(ts|tsx)$/, ''));
  return [...entries, ...walk(SRC).filter((f) => !isTest(f) && !testOnly(f))];
}

/** Every module specifier in a source file: static and dynamic imports, re-exports and require(). */
function specifiers(source: string): string[] {
  const re = /(?:\bfrom\s*|\bimport\s*\(\s*|\brequire\s*\(\s*|\bimport\s+)['"]([^'"]+)['"]/g;
  return [...source.matchAll(re)].map((m) => m[1]!);
}

/** Problems in one app file: imports of a test-only module, or use of a test-only name. */
function violations(file: string, source: string): string[] {
  const rel = path.relative(MOBILE, file);
  const out: string[] = [];
  for (const spec of specifiers(source)) {
    if (!spec.startsWith('.')) continue;
    const target = path.resolve(path.dirname(file), spec).replace(/\.(ts|tsx|js)$/, '');
    if (TEST_ONLY.includes(target)) out.push(`${rel} imports ${spec}`);
  }
  for (const [name, allowed] of Object.entries(TEST_ONLY_NAMES)) {
    if (!allowed.includes(rel) && new RegExp(`\\b${name}\\b`).test(source)) out.push(`${rel} uses ${name}`);
  }
  return out;
}

describe('no mock or demo data at runtime', () => {
  it('finds the app files it checks', () => {
    const files = runtimeFiles().map((f) => path.relative(MOBILE, f));
    expect(files).toEqual(expect.arrayContaining(['App.tsx', 'src/session.tsx', 'src/storage.ts', 'src/screens/ConnectScreen.tsx', 'src/photos/controller.tsx']));
    expect(files.some((f) => f.endsWith('.test.ts') || f.endsWith('.test.tsx'))).toBe(false);
    expect(files).not.toContain('src/api/mock.ts');
  });

  it('catches an import of the mock gateway, its fixtures or the in-memory Photos box', () => {
    const at = (rel: string) => path.join(MOBILE, rel);
    expect(violations(at('src/session.tsx'), "import { MockApi } from './api/mock';")).toEqual(['src/session.tsx imports ./api/mock', 'src/session.tsx uses MockApi']);
    expect(violations(at('src/screens/X.tsx'), "const f = require('../api/fixtures');")).toEqual(['src/screens/X.tsx imports ../api/fixtures']);
    expect(violations(at('src/photos/controller.tsx'), "export { x } from './mockServer';")).toEqual(['src/photos/controller.tsx imports ./mockServer']);
    expect(violations(at('App.tsx'), "import('./src/api/mock.ts')")).toEqual(['App.tsx imports ./src/api/mock.ts']);
    expect(violations(at('src/photos/controller.tsx'), 'const m = demoLibrary();')).toEqual(['src/photos/controller.tsx uses demoLibrary']);
    expect(violations(at('src/api/client.ts'), "import { Features } from './client';")).toEqual([]);
  });

  it('no app file imports api/mock, api/fixtures, photos/mockServer or the made-up photo library', () => {
    const found = runtimeFiles().flatMap((f) => violations(f, fs.readFileSync(f, 'utf8')));
    expect(found).toEqual([]);
  });
});
