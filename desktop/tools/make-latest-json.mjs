#!/usr/bin/env node
// SPDX-License-Identifier: Apache-2.0
// Builds the updater manifest (`latest.json`) from signed Tauri updater artifacts.
//   node tools/make-latest-json.mjs --dir <artifacts> --version 0.2.0 --base-url https://…/download/desktop-stable/ [--notes "…"] [--out latest.json]
// The signatures are the `.sig` files `tauri build` writes when TAURI_SIGNING_PRIVATE_KEY is set.
// It refuses: a missing .sig, a non-HTTPS base URL, a bad version, and an empty artifact set.
// It never signs anything and never reads the private key. See docs/UPDATER.md and README §Updates.
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const SEMVER = /^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$/;

/** Which updater platform key an artifact file name is for, or null. Tauri names: OneMind_0.2.0_aarch64.app.tar.gz, OneMind_0.2.0_x64-setup.exe, OneMind_0.2.0_amd64.AppImage. */
export function platformOf(name) {
  const n = name.toLowerCase();
  const arm = /aarch64|arm64/.test(n);
  if (n.endsWith('.app.tar.gz')) return arm ? 'darwin-aarch64' : 'darwin-x86_64';
  if (n.endsWith('-setup.exe')) return arm ? 'windows-aarch64' : 'windows-x86_64';
  if (n.endsWith('.appimage')) return arm ? 'linux-aarch64' : 'linux-x86_64';
  return null;
}

/**
 * @param {Record<string,string>} files  file name -> contents (only the .sig contents are read)
 * @param {{version:string, baseUrl:string, notes?:string, now?:Date}} o
 */
export function buildManifest(files, o) {
  if (!SEMVER.test(o.version || '')) throw new Error(`bad version: ${o.version}`);
  let base;
  try {
    base = new URL(o.baseUrl);
  } catch {
    throw new Error(`bad base url: ${o.baseUrl}`);
  }
  if (base.protocol !== 'https:' || base.username || base.password) throw new Error('base url must be https without credentials');
  const prefix = base.href.endsWith('/') ? base.href : `${base.href}/`;
  const platforms = {};
  for (const name of Object.keys(files).sort()) {
    const platform = platformOf(name);
    if (!platform) continue;
    const sigName = `${name}.sig`;
    const sig = files[sigName];
    if (typeof sig !== 'string' || !sig.trim()) throw new Error(`missing signature for ${name}: set TAURI_SIGNING_PRIVATE_KEY and build with bundle.createUpdaterArtifacts`);
    if (platforms[platform]) throw new Error(`two artifacts for ${platform}`);
    platforms[platform] = { signature: sig.trim(), url: prefix + encodeURIComponent(name) };
  }
  if (!Object.keys(platforms).length) throw new Error('no updater artifacts found');
  return { version: o.version, notes: o.notes || '', pub_date: (o.now || new Date()).toISOString(), platforms };
}

function main(argv) {
  const a = {};
  for (let i = 0; i < argv.length; i += 2) a[argv[i].replace(/^--/, '')] = argv[i + 1];
  if (!a.dir || !a.version || !a['base-url']) throw new Error('usage: --dir D --version V --base-url U [--notes N] [--out F]');
  const files = {};
  for (const f of readdirSync(a.dir)) if (platformOf(f) || f.endsWith('.sig')) files[f] = f.endsWith('.sig') ? readFileSync(`${a.dir}/${f}`, 'utf8') : '';
  const m = buildManifest(files, { version: a.version, baseUrl: a['base-url'], notes: a.notes });
  writeFileSync(a.out || 'latest.json', `${JSON.stringify(m, null, 2)}\n`);
  console.log(`wrote ${a.out || 'latest.json'}: ${Object.keys(m.platforms).join(', ')}`);
}

if (import.meta.url === pathToFileURL(process.argv[1] || '').href) {
  try {
    main(process.argv.slice(2));
  } catch (e) {
    console.error(`REFUSED: ${e.message}`);
    process.exit(2);
  }
}
