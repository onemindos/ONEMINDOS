// SPDX-License-Identifier: Apache-2.0
// "Honest about state" (docs/design/PRINCIPLES.md P2): a value is live only while its source
// keeps reporting. Contract §3: a node is stale after 30 s and offline after 120 s without a
// heartbeat. The same rule, with per-kind limits, is used for apps, backups and updates.
import type { Tone } from '../tokens/tokens';

export type Freshness = 'live' | 'stale' | 'offline' | 'unknown';

export interface FreshnessLimits {
  /** seconds after which the value is stale */
  staleAfter: number;
  /** seconds after which the source is considered gone */
  offlineAfter: number;
}

export const NODE_LIMITS: FreshnessLimits = { staleAfter: 30, offlineAfter: 120 };

export function freshness(ageSeconds: number, limits: FreshnessLimits = NODE_LIMITS): Freshness {
  if (!Number.isFinite(ageSeconds)) return 'unknown';
  if (ageSeconds > limits.offlineAfter) return 'offline';
  if (ageSeconds > limits.staleAfter) return 'stale';
  return 'live';
}

export const FRESHNESS_TONE: Record<Freshness, Tone> = {
  live: 'ok',
  stale: 'warn',
  offline: 'neutral',
  unknown: 'neutral',
};

export const FRESHNESS_LABEL: Record<Freshness, string> = {
  live: 'Online',
  stale: 'Stale',
  offline: 'Offline',
  unknown: 'Unknown',
};
