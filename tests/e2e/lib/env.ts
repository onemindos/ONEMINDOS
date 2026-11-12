// SPDX-License-Identifier: Apache-2.0
/**
 * Where the hub is and who we are. The harness (harness/run.sh) sets these; tokens are only ever
 * read from 0600 files, never from the command line or the environment value itself.
 */
import { readFileSync } from 'node:fs';

export interface HubEnv {
  url: string;
  ownerToken: string;
  agentToken: string | undefined;
  agentId: string;
  app: string;
  /** An app the harness leaves without a scan record, to prove the §10.3 gate in the UI. */
  unscannedApp: string;
  /** Executable that prints the hub's audit.jsonl (written by the harness). */
  auditFetch: string | undefined;
}

function readToken(path: string | undefined): string | undefined {
  if (!path) return undefined;
  return readFileSync(path, 'utf8').trim() || undefined;
}

/** The hub to test, or a reason why there is none (the suite then skips instead of failing). */
export function hubEnv(): HubEnv | { missing: string } {
  const url = process.env.E2E_HUB_URL?.replace(/\/+$/, '');
  if (!url) return { missing: 'E2E_HUB_URL is not set: run tests/e2e/harness/run.sh, which brings up a real hub' };
  const ownerToken = readToken(process.env.E2E_OWNER_TOKEN_FILE);
  if (!ownerToken) return { missing: 'E2E_OWNER_TOKEN_FILE is not set or empty' };
  return {
    url,
    ownerToken,
    agentToken: readToken(process.env.E2E_AGENT_TOKEN_FILE),
    agentId: process.env.E2E_AGENT_ID ?? 'e2e-agent',
    app: process.env.E2E_APP ?? 'ntfy',
    unscannedApp: process.env.E2E_UNSCANNED_APP ?? 'uptime-kuma',
    auditFetch: process.env.E2E_AUDIT_FETCH || undefined,
  };
}

/** How long an approval may take: the gateway runs `kubectl apply` inline (executor timeout 300 s). */
export const APPROVE_TIMEOUT_MS = 330_000;
