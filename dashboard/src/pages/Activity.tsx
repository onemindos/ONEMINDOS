// SPDX-License-Identifier: Apache-2.0
// Activity: the hash-chained audit log (GET /v1/audit/events, GET /v1/audit/verify) when this
// account may read it (the owner). Otherwise, or when the audit route cannot be read, it falls back
// to the requests on this hub (GET /v1/actions) and says so, never presenting that as the chain.
import { useCallback } from 'react';
import { AuditTimeline, type ActivityData, type SettingsLoadable } from '@onemind/ui';
import { toActivity } from '../data/audit';
import { useHub } from '../data/hub';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useActivity } from '../shell/Shell';

export const CHAIN_NOTE =
  'Built from the requests on this hub (GET /v1/actions). The hash-chained audit log, with sign-ins and settings changes, is only readable by the owner (GET /v1/audit/events).';

const PAGE = 200;

export function Activity() {
  const hub = useHub();
  const { api } = useSignedIn();
  const entries = useActivity();
  const audit = usePoll(
    useCallback(async () => {
      // Oldest-first API: ask for the verified head, then the last PAGE records before it.
      const verify = await api.auditVerify();
      const head = verify.head?.seq ?? 0;
      const records = await api.auditEvents({ limit: PAGE, after_seq: Math.max(0, head - PAGE) });
      return toActivity(records, verify);
    }, [api]),
    30_000,
  );

  if (audit.data) {
    const data: SettingsLoadable<ActivityData> = { status: 'ready', data: audit.data, asOf: new Date(audit.fetchedAt ?? Date.now()).toISOString() };
    return <AuditTimeline data={data} now={hub.now} onVerify={() => void audit.reload()} onRetry={() => void audit.reload()} />;
  }
  if (!audit.error && audit.loading) return <AuditTimeline data={{ status: 'loading' }} now={hub.now} chainNote={CHAIN_NOTE} calls={['GET /v1/audit/events']} />;

  const data: SettingsLoadable<ActivityData> =
    hub.actions.data !== undefined
      ? { status: 'ready', data: { entries }, asOf: hub.asOf ?? new Date().toISOString(), stale: hub.freshness === 'stale' || hub.freshness === 'offline' }
      : hub.actions.error
        ? { status: 'error', error: { error: 'unavailable', message: hub.actions.error.message } }
        : { status: 'loading' };
  return <AuditTimeline data={data} now={hub.now} onRetry={hub.reloadAll} chainNote={CHAIN_NOTE} calls={['GET /v1/actions']} />;
}
