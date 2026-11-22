// SPDX-License-Identifier: Apache-2.0
// Pre-flight for the iPhone release lane (mobile/docs/ios-release.md). Needs no Mac, no Apple account, no secrets.
// Checks the App Store rules that app.json controls: bundle id, 1024 px square PNG icons, export compliance flag,
// privacy manifest content. `expo prebuild` turns these into Info.plist and PrivacyInfo.xcprivacy; the
// release workflow then checks the generated files too.
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const PNG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
// Apple's "required reason API" categories (developer.apple.com/documentation/bundleresources/privacy-manifest-files)
const CATEGORIES = [
  'NSPrivacyAccessedAPICategoryFileTimestamp',
  'NSPrivacyAccessedAPICategoryUserDefaults',
  'NSPrivacyAccessedAPICategorySystemBootTime',
  'NSPrivacyAccessedAPICategoryDiskSpace',
];

export function pngSize(buf) {
  if (buf.length < 24 || !buf.subarray(0, 8).equals(PNG)) return null;
  return { width: buf.readUInt32BE(16), height: buf.readUInt32BE(20) };
}

/** Returns a list of problems; empty means ready. */
export function check(cfg, readAsset) {
  const bad = [];
  const ios = cfg?.expo?.ios ?? {};
  if (!/^[A-Za-z0-9.-]+$/.test(ios.bundleIdentifier ?? '')) bad.push('ios.bundleIdentifier missing or invalid');
  if (!cfg?.expo?.version) bad.push('expo.version missing (CFBundleShortVersionString)');
  const icons = [ios.icon?.light ?? ios.icon ?? cfg?.expo?.icon, ios.icon?.dark].filter(Boolean);
  if (!icons.length) bad.push('no iOS app icon configured');
  for (const f of icons) {
    let size;
    try {
      size = pngSize(readAsset(f));
    } catch {
      bad.push(`icon ${f} cannot be read`);
      continue;
    }
    if (!size) bad.push(`icon ${f} is not a PNG`);
    else if (size.width !== 1024 || size.height !== 1024) bad.push(`icon ${f} is ${size.width}x${size.height}, App Store needs 1024x1024`);
  }
  if (ios.config?.usesNonExemptEncryption !== false) {
    bad.push('ios.config.usesNonExemptEncryption must be false (ITSAppUsesNonExemptEncryption), or every upload waits on export-compliance answers');
  }
  const pm = ios.privacyManifests;
  if (!pm) bad.push('ios.privacyManifests missing (PrivacyInfo.xcprivacy)');
  else {
    if (pm.NSPrivacyTracking !== false) bad.push('NSPrivacyTracking must be false: OneMind does not track');
    if (!Array.isArray(pm.NSPrivacyCollectedDataTypes)) bad.push('NSPrivacyCollectedDataTypes must be listed (empty: nothing leaves for the developer)');
    const have = new Map((pm.NSPrivacyAccessedAPITypes ?? []).map((t) => [t.NSPrivacyAccessedAPIType, t.NSPrivacyAccessedAPITypeReasons ?? []]));
    for (const c of CATEGORIES) if (!have.get(c)?.length) bad.push(`privacy manifest has no reason for ${c}`);
  }
  if (!ios.infoPlist?.NSLocalNetworkUsageDescription) bad.push('NSLocalNetworkUsageDescription missing (hub on the local network)');
  return bad;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const given = process.argv.indexOf('--app-json');
  const cfg = JSON.parse(readFileSync(given > 0 ? process.argv[given + 1] : join(root, 'app.json'), 'utf8'));
  const bad = check(cfg, (f) => readFileSync(join(root, f)));
  if (bad.length) {
    for (const b of bad) console.error(`ios-release: ${b}`);
    process.exit(1);
  }
  console.log('ios-release: app.json is ready for an App Store build');
}
