// SPDX-License-Identifier: Apache-2.0
// Turns the ledger, rules and box answers into the words on the Backup screen. Honesty rules:
// - "on your OneMind" is not "backed up": the box's own backup and a restore check are separate
//   figures, and only restore-verified items may ever be freed from the phone (B1);
// - never say "all backed up" from an old scan or a failed run;
// - say why nothing is moving (rule, permission, connection), not just that it isn't.
import { formatAgo } from '../lib/time';
import type { Availability } from './discovery';
import type { Conditions, Progress } from './engine';
import { blockReason } from './engine';
import { counts, type BackupSettings, type Counts, type Ledger } from './ledger';
import type { MediaPermission } from './media';

export type Tone = 'ok' | 'warn' | 'bad' | 'info' | 'neutral';

export interface StatusView {
  headline: string;
  tone: Tone;
  lines: string[];
  counts: Counts;
  /** Why "Back up now" is disabled, if it is. */
  cannotRun?: string;
}

export interface StatusInput {
  availability: Availability;
  settings: BackupSettings;
  ledger: Ledger | null;
  permission: MediaPermission | undefined;
  conditions: Conditions | undefined;
  running: boolean;
  progress?: Progress;
  now: number;
}

const BLOCK_TEXT: Record<string, string> = {
  disabled: 'Backup is off',
  no_permission: 'OneMind cannot see your photos',
  offline: 'No network connection',
  needs_wifi: 'Waiting for Wi-Fi',
  needs_charging: 'Waiting for the phone to charge',
};

/** The same, inside a sentence. */
const BLOCK_PHRASE: Record<string, string> = {
  disabled: 'backup is off',
  no_permission: 'no photo access',
  offline: 'no network',
  needs_wifi: 'waiting for Wi-Fi',
  needs_charging: 'waiting for the phone to charge',
};

const REASON_TEXT: Record<string, string> = {
  ...BLOCK_TEXT,
  connection_lost: 'the connection to your OneMind dropped; it will continue where it stopped',
  time_up: 'the phone ended the background time; it will continue where it stopped',
  cancelled: 'stopped',
  unauthenticated: 'your OneMind did not accept this phone’s sign-in',
  permission_denied: 'your OneMind refused this phone',
  not_found: 'your OneMind does not know this phone’s backup source',
};

function ago(ms: number, now: number) {
  return formatAgo(Math.max(0, Math.floor((now - ms) / 1000)));
}

export function mb(n: number): string {
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)} GB`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(n / 1e3))} KB`;
}

export function summarize(x: StatusInput): StatusView {
  const c = counts(x.ledger);
  const L = x.ledger;
  const lines: string[] = [];
  const view = (headline: string, tone: Tone, cannotRun?: string): StatusView => ({ headline, tone, lines, counts: c, cannotRun });

  switch (x.availability.state) {
    case 'checking':
      return view('Looking for Photos on your OneMind…', 'neutral', 'Still checking your OneMind');
    case 'not_in_catalog':
      lines.push('This OneMind does not offer the Photos app yet. Nothing on this phone has been sent.');
      return view('Photos is not available on this OneMind', 'warn', 'Photos is not available');
    case 'not_installed':
      lines.push('Install Photos on your OneMind first (an owner approves it). Nothing on this phone has been sent.');
      return view('Photos is not installed on your OneMind', 'warn', 'Photos is not installed');
    case 'not_running':
      lines.push(`Photos on your OneMind reports “${x.availability.status.replace(/_/g, ' ')}”. Backup waits until it is running.`);
      return view('Photos is not running on your OneMind', 'warn', 'Photos is not running');
    case 'needs_https':
      lines.push('This phone reaches your OneMind over plain HTTP. Photos are only ever sent over HTTPS, so backup stays off until the connection is secure.');
      return view('Backup needs a secure connection', 'bad', 'Needs an HTTPS connection to your OneMind');
  }

  if (x.permission === 'denied') {
    lines.push('Allow photo access for OneMind in the phone’s Settings.');
    return view(BLOCK_TEXT.no_permission!, 'bad', BLOCK_TEXT.no_permission);
  }
  if (x.permission === 'limited') lines.push('You gave access to some photos only; items you did not pick are not backed up.');

  if (x.running) {
    const p = x.progress;
    if (!p) lines.push('Starting…');
    else {
      const phase = p.phase === 'uploading' ? 'Uploading' : p.phase === 'hashing' ? 'Checking files' : p.phase === 'checking' ? 'Asking your OneMind' : 'Looking at your library';
      lines.push(`${phase}. ${p.done} of ${p.total} selected items are on your OneMind.`);
    }
    return view('Backing up…', 'info', 'A backup is running');
  }

  const block = x.conditions ? blockReason(x.settings, x.conditions) : x.settings.enabled ? undefined : 'disabled';
  const run = L?.lastRun;

  if (!L?.scan) {
    lines.push('Nothing has been sent from this phone yet.');
    if (block === 'disabled') lines.push('Turn backup on to send your photos and videos to your OneMind.');
    return view(block ? BLOCK_TEXT[block]! : 'Not backed up yet', block === 'disabled' ? 'neutral' : block ? 'warn' : 'info', block ? BLOCK_TEXT[block] : undefined);
  }

  lines.push(`${c.done} of ${c.total} selected items are on your OneMind${L.scan ? ` (library checked ${ago(L.scan.at, x.now)})` : ''}.`);
  if (c.failed) lines.push(`${c.failed} could not be sent; see the list below.`);
  if (run && run.outcome !== 'completed' && run.reason && !(run.reason in BLOCK_TEXT) && (c.waiting || c.failed))
    lines.push(`Last attempt ${ago(run.endedAt, x.now)}: ${REASON_TEXT[run.reason] ?? run.message ?? run.reason}.`);
  if (L.lastComplete) lines.push(`Everything selected was last confirmed on your OneMind ${ago(L.lastComplete, x.now)}.`);

  let headline: string;
  let tone: Tone;
  if (block) {
    headline = c.waiting ? `${c.waiting} waiting · ${BLOCK_PHRASE[block]}` : BLOCK_TEXT[block]!;
    tone = block === 'disabled' ? 'neutral' : 'warn';
  } else if (c.waiting === 0 && c.failed === 0) {
    headline = `All ${c.total} selected items are on your OneMind`;
    tone = 'ok';
  } else if (c.waiting === 0) {
    headline = `${c.failed} item${c.failed === 1 ? '' : 's'} could not be sent`;
    tone = 'bad';
  } else {
    headline = `${c.waiting} waiting to be sent`;
    tone = run && run.outcome === 'error' ? 'bad' : 'info';
  }
  return view(headline, tone, block ? BLOCK_TEXT[block] : undefined);
}
