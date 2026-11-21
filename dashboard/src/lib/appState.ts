// SPDX-License-Identifier: Apache-2.0
// The one state dot on an app's page (FD-06). It combines four facts: health, restarts, the last
// security scan and a waiting update. A fact that could not be read turns the dot grey ("unknown")
// instead of green: a dot must never claim more than the hub told us. A fault we do know of still
// wins over an unread fact. Update status is "absent" on a gateway that does not report it yet;
// once a source exists and fails, it counts like the others.
import type { ScanSummary } from '../api/types';

/** A fact the page tried to read: it arrived, it failed, or this gateway does not offer it. */
export type Fact<T> = { state: 'ok'; value: T } | { state: 'failed' } | { state: 'absent' };

export type AppDot = 'ok' | 'warn' | 'bad' | 'neutral' | 'unknown';

export interface AppHealth {
  /** GET /v1/apps/{id} health.state: healthy, unhealthy, starting, stopped or unknown. */
  state: string;
  reason: string | null;
  /** Container restarts summed over the app's components. */
  restarts: number;
}

export interface AppStateInput {
  /** The catalog's lifecycle status (GET /v1/apps): installed, stopped, updating, failed ... */
  status: Fact<string>;
  health: Fact<AppHealth>;
  /** Last security scan (GET /v1/apps); a never-scanned app is `ok` with null. */
  scan: Fact<ScanSummary | null>;
  /** Is a newer version waiting? */
  update: Fact<boolean>;
}

export interface AppState {
  dot: AppDot;
  label: string;
  /** Plain-words reasons, worst first. */
  reasons: string[];
}

/** This many restarts or more are called out; a few are normal after an update or a reboot. */
export const RESTART_WARN = 3;
export const SCAN_STALE_MS = 7 * 24 * 3600_000;
const BUSY = new Set(['starting', 'stopping', 'restarting', 'configuring', 'installing', 'updating', 'removing', 'reverting']);
const LABEL: Record<AppDot, string> = { ok: 'Healthy', warn: 'Needs a look', bad: 'Problem', neutral: 'Stopped', unknown: 'Unknown' };

export function appState(i: AppStateInput, now: number): AppState {
  const bad: string[] = [];
  const warn: string[] = [];
  const unknown: string[] = [];
  let stopped = false;

  if (i.status.state !== 'ok') unknown.push('The hub did not report this app’s status.');
  else {
    const s = i.status.value;
    if (s === 'failed') bad.push('The app has failed.');
    else if (s === 'stopped') stopped = true;
    else if (BUSY.has(s)) warn.push(`The app is ${s}.`);
    else if (s === 'drifted') warn.push('What runs no longer matches what was approved.');
    else if (s === 'unknown') unknown.push('The hub does not know this app’s status.');
  }

  if (i.health.state !== 'ok') unknown.push('Health could not be read.');
  else {
    const h = i.health.value;
    const why = h.reason ? ` (${h.reason})` : '';
    if (h.state === 'unhealthy') bad.push(`It is not healthy${why}.`);
    else if (h.state === 'starting') warn.push(`It is not ready yet${why}.`);
    else if (h.state === 'stopped') stopped = true;
    else if (h.state === 'unknown') unknown.push(`Health is unknown${why}.`);
    else if (h.state !== 'healthy') unknown.push(`The hub reports the health “${h.state}”, which this screen does not know.`);
    if (h.restarts >= RESTART_WARN) warn.push(`It has restarted ${h.restarts} times.`);
  }

  if (i.scan.state === 'failed') unknown.push('The security scan could not be read.');
  else if (i.scan.state === 'ok') {
    const scan = i.scan.value;
    const at = scan ? Date.parse(scan.scanned_at) : NaN;
    if (!scan) warn.push('It has never been scanned.');
    else if (scan.result !== 'pass') bad.push('It failed its last security scan.');
    else if (Number.isNaN(at)) unknown.push('The scan date is not valid.');
    else if (now - at > SCAN_STALE_MS) warn.push('Its last scan is more than 7 days old.');
  }

  if (i.update.state === 'failed') unknown.push('Update status could not be read.');
  else if (i.update.state === 'ok' && i.update.value) warn.push('An update is waiting. An owner approves it.');

  const dot: AppDot = bad.length ? 'bad' : unknown.length ? 'unknown' : warn.length ? 'warn' : stopped ? 'neutral' : 'ok';
  return { dot, label: LABEL[dot], reasons: [...bad, ...unknown, ...warn] };
}
