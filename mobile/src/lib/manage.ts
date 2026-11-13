// SPDX-License-Identifier: Apache-2.0
// What the phone sends for the box-management screens (contract §12.12, §12.17, §12.40, §12.41).
// The rule is the same everywhere: the phone only FILES a request and shows its approval state.
// Nothing here approves, and a request is sent with the plan hash the person was shown.
import type { OneMindApi } from '../api/client';
import {
  ApiError,
  type Action,
  type BackupDestination,
  type CatalogApp,
  type FirstRunSettingsBody,
  type LifecycleType,
  type PlanPreview,
} from '../api/types';
import { REQUEST_TTL_MS } from './approvals';
import { uuidv4 } from './uuid';

/** App statuses (§3, §12.15, §12.40) in which a lifecycle action would collide with one already running. */
const BUSY = new Set(['starting', 'stopping', 'restarting', 'updating', 'configuring', 'deleting_data', 'reverting']);

export function isBusy(status: string): boolean {
  return BUSY.has(status);
}

/** The lifecycle requests that make sense for an installed app in this status. The hub still checks. */
export function lifecycleOptions(app: Pick<CatalogApp, 'installed' | 'status'>): LifecycleType[] {
  if (!app.installed || isBusy(app.status)) return [];
  if (app.status === 'stopped') return ['app.start', 'app.remove'];
  return ['app.stop', 'app.restart', 'app.update', 'app.remove'];
}

export const LIFECYCLE_LABEL: Record<LifecycleType | 'app.install', string> = {
  'app.install': 'Install',
  'app.start': 'Start',
  'app.stop': 'Stop',
  'app.restart': 'Restart',
  'app.update': 'Update',
  'app.remove': 'Remove',
};

/** What the plan preview said, ready for the confirmation card. `refused` means the hub will not file it. */
export interface LifecyclePreview {
  preview: PlanPreview;
  refused: boolean;
}

export async function previewLifecycle(api: OneMindApi, appId: string, type: LifecycleType): Promise<LifecyclePreview> {
  const preview = await api.appPlan(appId, type);
  return { preview, refused: preview.policy_verdict === 'refused' };
}

/**
 * File the request, bound to the plan that was shown (§12.40: the hub answers 409 `plan_changed` if the
 * fresh plan differs). The result is an action `awaiting_approval`; an owner decides it in Approvals.
 */
export function requestLifecycle(
  api: OneMindApi,
  appId: string,
  type: LifecycleType,
  planSha256: string,
  opts: { now?: number; idempotencyKey?: string } = {},
): Promise<Action> {
  return api.createAction({
    type,
    params: { app_id: appId },
    idempotency_key: opts.idempotencyKey ?? uuidv4(),
    expires_at: new Date((opts.now ?? Date.now()) + REQUEST_TTL_MS).toISOString(),
    plan_sha256: planSha256,
  });
}

/** One plain sentence for a failed request, from the §12.2 code and reason. */
export function requestError(e: unknown, what = 'that'): { text: string; forbidden: boolean } {
  const err = e instanceof ApiError ? e : new ApiError(0, 'unknown', String(e));
  if (err.reason === 'plan_changed') return { text: `The plan for ${what} changed. Nothing was sent; look at the new plan and try again.`, forbidden: false };
  switch (err.code) {
    case 'permission_denied':
      return { text: `This sign-in may not do ${what}. Only an owner can.`, forbidden: true };
    case 'conflict':
      return { text: `The hub refused ${what} because the app is busy or the request already exists.`, forbidden: false };
    case 'rate_limited':
      return { text: `The hub asks to slow down${err.retryAfterS ? `; try again in ${err.retryAfterS} s` : ''}.`, forbidden: false };
    case 'policy_refused':
      return { text: `The install sandbox refused ${what}: ${err.message}`, forbidden: false };
    case 'network':
      return { text: `Could not reach the hub: ${err.message}. Nothing was changed.`, forbidden: false };
    case 'not_found':
      return { text: `The hub does not have ${what}.`, forbidden: false };
    default:
      return { text: `Could not do ${what}: ${err.message}`, forbidden: false };
  }
}

// ---- first-run settings (§12.41) ----

/** Lower-case RFC 1123 label, 1 to 63 characters, no leading or trailing hyphen. */
export function validBoxName(v: string): boolean {
  return /^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$/.test(v);
}

/** §12.41: choice `usb` needs a `usb` destination, `peer` a `box` one and `s3` an `s3` one. */
export const CHOICE_KIND: Record<'usb' | 'peer' | 's3', string> = { usb: 'usb', peer: 'box', s3: 's3' };

export function destinationsFor(choice: FirstRunSettingsBody['backup_choice'], all: BackupDestination[]): BackupDestination[] {
  return choice === 'later' ? [] : all.filter((d) => d.kind === CHOICE_KIND[choice]);
}

/** Problems the phone can see before sending; the hub validates again and writes nothing on a refusal. */
export function settingsProblem(b: FirstRunSettingsBody, destinations: BackupDestination[]): string | undefined {
  if (!validBoxName(b.box_name)) return 'The box name uses lower-case letters, digits and hyphens, 1 to 63 characters, and cannot start or end with a hyphen.';
  if (!b.time_zone.trim() || /\s/.test(b.time_zone) || b.time_zone.startsWith('/')) return 'Enter a time zone like Europe/Berlin, or UTC.';
  if (b.backup_choice === 'later' && b.backup_destination_id) return 'A destination does not go with "later".';
  if (b.backup_destination_id && !destinationsFor(b.backup_choice, destinations).some((d) => d.id === b.backup_destination_id))
    return 'That destination does not match the backup choice.';
  return undefined;
}

export function formatBytes(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return 'unknown';
  const u = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let v = n;
  while (v >= 1000 && i < u.length - 1) {
    v /= 1000;
    i++;
  }
  return `${i === 0 ? v : v.toFixed(v < 10 ? 1 : 0)} ${u[i]}`;
}
