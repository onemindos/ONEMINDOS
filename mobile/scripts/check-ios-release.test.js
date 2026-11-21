// SPDX-License-Identifier: Apache-2.0
// The iPhone release pre-flight (scripts/check-ios-release.mjs) passes on the real app.json and fails on each
// App Store rule it guards. It runs as a child process so it is tested exactly as CI runs it.
const { execFileSync } = require('node:child_process');
const { mkdtempSync, readFileSync, writeFileSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');

const script = join(__dirname, 'check-ios-release.mjs');
const real = JSON.parse(readFileSync(join(__dirname, '..', 'app.json'), 'utf8'));

function run(cfg) {
  const dir = mkdtempSync(join(tmpdir(), 'ios-release-'));
  const file = join(dir, 'app.json');
  writeFileSync(file, JSON.stringify(cfg));
  try {
    // icons are resolved against mobile/, so the real assets are used
    const out = execFileSync('node', [script, '--app-json', file], { encoding: 'utf8', stdio: 'pipe' });
    return { code: 0, out };
  } catch (e) {
    return { code: e.status, out: e.stderr };
  }
}
const mutate = (fn) => {
  const c = JSON.parse(JSON.stringify(real));
  fn(c);
  return run(c);
};

describe('iPhone release pre-flight', () => {
  it('passes on the real app.json', () => {
    expect(run(real).code).toBe(0);
  });
  it('fails without the export compliance flag', () => {
    const r = mutate((c) => delete c.expo.ios.config);
    expect(r.code).toBe(1);
    expect(r.out).toContain('usesNonExemptEncryption');
  });
  it('fails without a privacy manifest', () => {
    const r = mutate((c) => delete c.expo.ios.privacyManifests);
    expect(r.code).toBe(1);
    expect(r.out).toContain('privacyManifests');
  });
  it('fails when a required-reason category has no reason', () => {
    const r = mutate((c) => (c.expo.ios.privacyManifests.NSPrivacyAccessedAPITypes = []));
    expect(r.code).toBe(1);
    expect(r.out).toContain('NSPrivacyAccessedAPICategoryDiskSpace');
  });
  it('fails if tracking is switched on', () => {
    expect(mutate((c) => (c.expo.ios.privacyManifests.NSPrivacyTracking = true)).code).toBe(1);
  });
  it('fails on a wrong-size icon', () => {
    const r = mutate((c) => (c.expo.ios.icon.light = './assets/brand/missing.png'));
    expect(r.code).toBe(1);
  });
});
