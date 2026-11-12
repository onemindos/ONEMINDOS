// SPDX-License-Identifier: Apache-2.0
/**
 * Golden path, audit (contract §3 "Audit"): after the runs above, the whole hash chain on the hub
 * re-verifies, and it names who asked and who approved. The harness hands us the file through
 * E2E_AUDIT_FETCH (an executable that prints audit.jsonl); once GET /v1/audit/verify ships
 * (§12.16, CORE-SEC-6 / DEV-API-9) the gateway's own answer is checked as well.
 */
import { execFileSync } from 'node:child_process';
import { expect, test } from '@playwright/test';
import { verifyChain, type AuditRecord } from '../lib/audit';
import { hubEnv, type HubEnv } from '../lib/env';
import { Hub } from '../lib/hub';

const env = hubEnv();
const E = env as HubEnv;
test.skip('missing' in env, 'missing' in env ? env.missing : '');

function approvedBy(records: AuditRecord[], actionId: string) {
  return records.find((r) => r.event === 'action.approved' && r.action_id === actionId)?.principal;
}

test('the audit chain on the hub verifies and records requester and approver', async () => {
  test.skip(!E.auditFetch, 'E2E_AUDIT_FETCH is not set: the harness provides it (reads audit.jsonl on the hub)');
  const text = execFileSync(E.auditFetch!, { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 });
  const chain = verifyChain(text);
  expect(chain.problem, `audit chain broke at line ${chain.firstBadLine}`).toBeUndefined();
  expect(chain.ok).toBe(true);
  const recs = chain.records;

  const requested = recs.filter(
    (r) => r.event === 'action.requested' && (r.data as { params?: { app_id?: string } }).params?.app_id === E.app,
  );
  // Owner flow (01) and agent flow (02): installs and removals by both kinds of principal.
  const byOwner = requested.filter((r) => r.principal?.kind === 'person' && r.principal.role === 'owner');
  expect(byOwner.length).toBeGreaterThanOrEqual(2);
  if (E.agentToken) {
    const byAgent = requested.filter((r) => r.principal?.kind === 'agent' && r.principal.id === E.agentId);
    expect(byAgent.map((r) => (r.data as { type: string }).type)).toEqual(
      expect.arrayContaining(['app.install', 'app.remove']),
    );
    for (const r of byAgent) {
      expect(approvedBy(recs, r.action_id!)).toMatchObject({ kind: 'person', role: 'owner' });
      expect(recs.some((x) => x.event === 'action.succeeded' && x.action_id === r.action_id)).toBe(true);
    }
    // The agent tried to approve its own request; the refusal is audited.
    expect(recs.some((r) => r.event === 'authz.denied' && r.principal?.id === E.agentId)).toBe(true);
  }
  for (const r of byOwner) expect(approvedBy(recs, r.action_id!)).toMatchObject({ kind: 'person', role: 'owner' });
});

test('GET /v1/audit/verify agrees (§12.16)', async ({ request }) => {
  const hub = new Hub(request, E.url, E.ownerToken);
  const paths = await hub.openapiPaths();
  test.skip(!paths.has('/v1/audit/verify'), 'not merged yet: audit API (§12.16; CORE-SEC-6, DEV-API-9)');
  const v = await hub.get<{ ok: boolean; records: number; first_bad_seq: number | null }>('/v1/audit/verify');
  expect(v.ok).toBe(true);
  expect(v.records).toBeGreaterThan(0);
  expect(v.first_bad_seq ?? null).toBeNull();
});
