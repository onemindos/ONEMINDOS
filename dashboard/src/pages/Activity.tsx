// SPDX-License-Identifier: Apache-2.0
// Activity: every request, decision and result on this hub, newest first. Built from
// GET /v1/actions until the audit route lands (§12, CORE-SEC-6); the screen says it is not the
// hash-chained audit log.
import { AuditTimeline, type ActivityData, type SettingsLoadable } from '@onemind/ui';
import { useHub } from '../data/hub';
import { useActivity } from '../shell/Shell';

export const CHAIN_NOTE =
  'Built from the requests on this hub (GET /v1/actions). The hash-chained audit log, with sign-ins and settings changes, comes with CORE-SEC-6 (GET /v1/audit/events, GET /v1/audit/verify).';

export function Activity() {
  const hub = useHub();
  const entries = useActivity();
  const data: SettingsLoadable<ActivityData> =
    hub.actions.data !== undefined
      ? { status: 'ready', data: { entries }, asOf: hub.asOf ?? new Date().toISOString(), stale: hub.freshness === 'stale' || hub.freshness === 'offline' }
      : hub.actions.error
        ? { status: 'error', error: { error: 'unavailable', message: hub.actions.error.message } }
        : { status: 'loading' };
  return <AuditTimeline data={data} now={hub.now} onRetry={hub.reloadAll} chainNote={CHAIN_NOTE} calls={['GET /v1/actions']} />;
}
