// SPDX-License-Identifier: Apache-2.0
// Build-time apps catalog: reads apps/<id>/onemind.app.yaml (contract sdk/contracts/poc-v0.md §4,
// §9.3, §11.2) and apps/<id>/scan.json when present (§11.1). Nothing here is hand-maintained:
// adding an app directory adds a catalog page on the next build.
import fs from 'node:fs';
import path from 'node:path';
import { parse } from 'yaml';

/** The repository's apps/ directory. `npm run build` runs from site/, so it is ../apps. */
export const APPS_DIR = process.env.ONEMIND_APPS_DIR
  ? path.resolve(process.env.ONEMIND_APPS_DIR)
  : path.resolve(process.cwd(), '..', 'apps');

const REPO = 'https://github.com/onemindos/ONEMINDOS';
const SCAN_MAX_AGE_DAYS = 7; // contract §10.3: no install without a passing scan newer than 7 days

export type ScanImage = {
  ref: string;
  archs?: string[];
  trivy?: { version?: string; critical_fixable?: number; critical?: number; high?: number };
  clamav?: { signatures?: string; infected?: number };
  secrets?: number;
  cosign?: 'verified' | 'unsigned' | 'failed';
};

export type Scan = {
  scanned_at: string;
  result: 'pass' | 'fail';
  images: ScanImage[];
  licence?: { spdx?: string; class?: 'L1' | 'L2' | 'blocked' };
  smoke?: 'pass' | 'fail' | 'skipped';
};

export type Check = { label: string; state: 'ok' | 'warn' | 'fail' | 'unknown'; detail: string };

export type App = {
  id: string;
  name: string;
  version: string;
  description: string;
  category: string;
  license: string;
  source: string;
  archs: string[];
  minMemoryMb?: number;
  gpu: boolean;
  webPort?: number;
  links: Record<string, string>;
  tier?: string;
  updates?: { channel?: string; automerge?: string };
  agentPrincipal: boolean;
  images: string[];
  iconDataUri?: string;
  scan: Scan | null;
  repoPath: string;
  checks: Check[];
  installable: { ok: boolean; reason: string };
};

function readIfExists(file: string): string | null {
  try {
    return fs.readFileSync(file, 'utf8');
  } catch {
    return null;
  }
}

/** Every `image:` reference in the app's manifests directory (one level, *.yaml / *.yml). */
function manifestImages(dir: string): string[] {
  if (!fs.existsSync(dir)) return [];
  const refs = new Set<string>();
  for (const f of fs.readdirSync(dir).sort()) {
    if (!/\.ya?ml$/.test(f)) continue;
    const text = fs.readFileSync(path.join(dir, f), 'utf8');
    for (const m of text.matchAll(/^\s*-?\s*image:\s*["']?([^\s"'#]+)/gm)) refs.add(m[1]);
  }
  return [...refs];
}

function daysSince(iso: string, now: Date): number {
  return (now.getTime() - new Date(iso).getTime()) / 86_400_000;
}

/** The trust card: what a visitor (and the gateway) can check about this app, from files in Git. */
function trustChecks(app: Omit<App, 'checks' | 'installable'>, now: Date): Check[] {
  const checks: Check[] = [];
  const s = app.scan;
  const cls = s?.licence?.class;
  checks.push({
    label: 'Licence',
    state: cls === 'blocked' ? 'fail' : cls ? 'ok' : 'unknown',
    detail: cls ? `${s?.licence?.spdx ?? app.license}, class ${cls}` : `${app.license} (declared; class set by the CI gate)`,
  });
  const pinned = app.images.length > 0 && app.images.every((r) => r.includes('@sha256:'));
  checks.push({
    label: 'Images pinned by digest',
    state: app.images.length === 0 ? 'unknown' : pinned ? 'ok' : 'warn',
    detail: app.images.length === 0 ? 'no image found in manifests/' : pinned ? `${app.images.length} image(s), tag + digest` : 'at least one image is not digest-pinned',
  });
  if (!s) {
    for (const label of ['Vulnerabilities', 'Malware', 'Secrets in image', 'Signature', 'Smoke test'])
      checks.push({ label, state: 'unknown', detail: 'no scan record yet' });
    return checks;
  }
  const sum = (f: (i: ScanImage) => number | undefined) => s.images.reduce((n, i) => n + (f(i) ?? 0), 0);
  const critFix = sum((i) => i.trivy?.critical_fixable);
  const crit = sum((i) => i.trivy?.critical);
  const high = sum((i) => i.trivy?.high);
  checks.push({
    label: 'Vulnerabilities',
    state: critFix > 0 ? 'fail' : crit > 0 ? 'warn' : 'ok',
    detail: `Trivy: ${crit} critical (${critFix} fixable), ${high} high`,
  });
  const infected = sum((i) => i.clamav?.infected);
  checks.push({ label: 'Malware', state: infected > 0 ? 'fail' : 'ok', detail: `ClamAV: ${infected} hit(s)` });
  const secrets = sum((i) => i.secrets);
  checks.push({ label: 'Secrets in image', state: secrets > 0 ? 'fail' : 'ok', detail: `${secrets} finding(s)` });
  const cos = s.images.map((i) => i.cosign ?? 'unsigned');
  checks.push({
    label: 'Signature',
    state: cos.includes('failed') ? 'fail' : cos.every((c) => c === 'verified') ? 'ok' : 'warn',
    detail: cos.every((c) => c === 'verified') ? 'cosign verified' : cos.includes('failed') ? 'cosign verification failed' : 'upstream does not sign its image',
  });
  checks.push({
    label: 'Smoke test',
    state: s.smoke === 'pass' ? 'ok' : s.smoke === 'fail' ? 'fail' : 'warn',
    detail: s.smoke ?? 'not recorded',
  });
  const age = daysSince(s.scanned_at, now);
  checks.push({
    label: 'Scan age',
    state: age <= SCAN_MAX_AGE_DAYS ? 'ok' : 'warn',
    detail: `${s.scanned_at.slice(0, 10)} (${Math.max(0, Math.floor(age))} days before this page was built)`,
  });
  return checks;
}

function installable(scan: Scan | null, now: Date): App['installable'] {
  if (!scan) return { ok: false, reason: 'No scan record yet: the gateway refuses to install it (contract §11.1).' };
  if (scan.result !== 'pass') return { ok: false, reason: 'The last scan did not pass.' };
  if (daysSince(scan.scanned_at, now) > SCAN_MAX_AGE_DAYS)
    return { ok: false, reason: `The last passing scan is older than ${SCAN_MAX_AGE_DAYS} days.` };
  return { ok: true, reason: 'Passing scan within the last 7 days.' };
}

let cache: App[] | null = null;

export function loadApps(now = new Date()): App[] {
  if (cache) return cache;
  if (!fs.existsSync(APPS_DIR)) throw new Error(`apps directory not found: ${APPS_DIR} (set ONEMIND_APPS_DIR)`);
  const apps: App[] = [];
  for (const dirName of fs.readdirSync(APPS_DIR).sort()) {
    if (dirName.startsWith('_') || dirName.startsWith('.')) continue;
    const dir = path.join(APPS_DIR, dirName);
    const raw = readIfExists(path.join(dir, 'onemind.app.yaml'));
    if (raw === null) continue;
    const doc = parse(raw) ?? {};
    const md = doc.metadata ?? {};
    const spec = doc.spec ?? {};
    for (const k of ['id', 'name', 'version', 'description', 'license', 'source'])
      if (!md[k]) throw new Error(`apps/${dirName}/onemind.app.yaml: metadata.${k} is missing`);
    if (md.id !== dirName) throw new Error(`apps/${dirName}: metadata.id "${md.id}" does not match the directory`);

    const icon = md.icon ? readIfExists(path.join(dir, md.icon)) : null;
    const scanRaw = readIfExists(path.join(dir, 'scan.json'));
    let scan: Scan | null = null;
    if (scanRaw !== null) {
      try {
        scan = JSON.parse(scanRaw) as Scan;
      } catch (e) {
        throw new Error(`apps/${dirName}/scan.json is not valid JSON: ${(e as Error).message}`);
      }
    }
    // Only https links reach the page: a manifest is data, and an href is not the place to trust it.
    const links: Record<string, string> = Object.fromEntries(
      Object.entries((md.links ?? {}) as Record<string, unknown>).filter(
        (e): e is [string, string] => typeof e[1] === 'string' && /^https:\/\//.test(e[1]),
      ),
    );
    if (!links.github && /^https:\/\/github\.com\//.test(md.source)) links.github = md.source;

    const base = {
      id: md.id as string,
      name: md.name as string,
      version: String(md.version),
      description: md.description as string,
      category: (md.category as string) ?? 'other',
      license: md.license as string,
      source: md.source as string,
      archs: (spec.archs as string[]) ?? [],
      minMemoryMb: spec.requires?.minMemoryMb,
      gpu: Boolean(spec.requires?.gpu),
      webPort: spec.web?.port,
      links,
      tier: md.tier,
      updates: spec.updates,
      agentPrincipal: Boolean(spec.agent?.principal),
      images: manifestImages(path.join(dir, String(spec.manifests ?? 'manifests/'))),
      iconDataUri:
        icon && md.icon.endsWith('.svg') ? `data:image/svg+xml;base64,${Buffer.from(icon).toString('base64')}` : undefined,
      scan,
      repoPath: `${REPO}/tree/main/apps/${dirName}`,
    };
    apps.push({ ...base, checks: trustChecks(base, now), installable: installable(scan, now) });
  }
  cache = apps;
  return apps;
}
