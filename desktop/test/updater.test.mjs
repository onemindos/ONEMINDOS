// SPDX-License-Identifier: Apache-2.0
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildManifest, platformOf } from '../tools/make-latest-json.mjs';

const conf = JSON.parse(readFileSync(new URL('../src-tauri/tauri.conf.json', import.meta.url), 'utf8'));
const BASE = 'https://github.com/onemindos/ONEMINDOS/releases/download/desktop-stable/';
const now = new Date('2026-12-01T10:00:00Z');

test('config: only the public key lives in tauri.conf.json; endpoints are compiled into Rust', () => {
  const u = conf.plugins.updater;
  assert.deepEqual(Object.keys(u), ['pubkey']);
  assert.ok(u.pubkey && !/PRIVATE/i.test(u.pubkey));
  // A private key is only present in CI; with this flag on, an unsigned local build would fail.
  assert.notEqual(conf.bundle.createUpdaterArtifacts, true);
});

test('config: the web view gets no updater permission (Rust drives the plugin)', () => {
  const cap = readFileSync(new URL('../src-tauri/capabilities/default.json', import.meta.url), 'utf8');
  assert.doesNotMatch(cap, /updater/);
});

test('platformOf maps Tauri artifact names', () => {
  assert.equal(platformOf('OneMind_0.2.0_aarch64.app.tar.gz'), 'darwin-aarch64');
  assert.equal(platformOf('OneMind_0.2.0_x64.app.tar.gz'), 'darwin-x86_64');
  assert.equal(platformOf('OneMind.app.tar.gz', 'aarch64'), 'darwin-aarch64');
  assert.equal(platformOf('OneMind.app.tar.gz', 'x86_64'), 'darwin-x86_64');
  assert.throws(() => platformOf('OneMind.app.tar.gz'), /--mac-arch/);
  assert.equal(platformOf('OneMind_0.2.0_x64-setup.exe'), 'windows-x86_64');
  assert.equal(platformOf('OneMind_0.2.0_amd64.AppImage'), 'linux-x86_64');
  assert.equal(platformOf('OneMind_0.2.0_aarch64.dmg'), null);
  assert.equal(platformOf('OneMind_0.2.0_x64-setup.exe.sig'), null);
});

test('buildManifest: signed artifacts become platform entries', () => {
  const m = buildManifest(
    {
      'OneMind_0.2.0_aarch64.app.tar.gz': '',
      'OneMind_0.2.0_aarch64.app.tar.gz.sig': 'SIG-MAC\n',
      'OneMind_0.2.0_x64-setup.exe': '',
      'OneMind_0.2.0_x64-setup.exe.sig': 'SIG-WIN',
      'OneMind_0.2.0_aarch64.dmg': '',
    },
    { version: '0.2.0', baseUrl: BASE, notes: 'n', now },
  );
  assert.equal(m.version, '0.2.0');
  assert.equal(m.pub_date, '2026-12-01T10:00:00.000Z');
  assert.deepEqual(Object.keys(m.platforms), ['darwin-aarch64', 'windows-x86_64']);
  assert.equal(m.platforms['darwin-aarch64'].signature, 'SIG-MAC');
  assert.equal(m.platforms['windows-x86_64'].url, `${BASE}OneMind_0.2.0_x64-setup.exe`);
});

test('buildManifest refuses unsigned, insecure, empty and malformed input', () => {
  const art = { 'a_x64-setup.exe': '' };
  assert.throws(() => buildManifest(art, { version: '0.2.0', baseUrl: BASE }), /missing signature/);
  assert.throws(() => buildManifest({ ...art, 'a_x64-setup.exe.sig': ' ' }, { version: '0.2.0', baseUrl: BASE }), /missing signature/);
  const ok = { ...art, 'a_x64-setup.exe.sig': 's' };
  assert.throws(() => buildManifest(ok, { version: '0.2.0', baseUrl: 'http://example.com/' }), /https/);
  assert.throws(() => buildManifest(ok, { version: 'latest', baseUrl: BASE }), /bad version/);
  assert.throws(() => buildManifest({ 'x.dmg': '' }, { version: '0.2.0', baseUrl: BASE }), /no updater artifacts/);
  assert.throws(() => buildManifest({ ...ok, 'b_x64-setup.exe': '', 'b_x64-setup.exe.sig': 's' }, { version: '0.2.0', baseUrl: BASE }), /two artifacts/);
});
