// SPDX-License-Identifier: Apache-2.0
// Shared plumbing for Settings > Permissions (gateway permissions design §3.5 to §3.8, §3.12).
// Every call goes through @onemind/sdk with the signed-in person's token. The gateway decides who may
// change what; this file only carries the request and, when the gateway asks for it, the passkey.
//
// Current gateways send permission-increasing changes to Approvals. Older gateways may answer
// 401 step_up_required. The page uses the same passkey sign-in as the sign-in page and retries once.
import { useCallback, useMemo } from 'react';
import { OneMind, OneMindError, type Action } from '@onemind/sdk';
import { ApiError } from '../api/types';
import { useSignedIn } from '../session';
import { getPasskey, webauthnSupported } from './webauthn';

export const MODES = ['locked', 'ask', 'remember', 'auto', 'headless'] as const;
export type Mode = (typeof MODES)[number];

/** Plain names and one line each, for a first-time owner (design §3.5). */
export const MODE_TEXT: Record<string, { label: string; help: string }> = {
  locked: { label: 'Locked', help: 'Every request is refused at once. Requests already waiting are cancelled.' },
  ask: { label: 'Always ask', help: 'Every request waits for you. Rules are ignored. This is where everyone starts.' },
  remember: { label: 'Ask once, then remember', help: 'Requests wait for you, and you can approve and remember similar ones.' },
  auto: { label: 'Auto within rules', help: 'Requests your rules cover go through. Everything else waits for you.' },
  headless: { label: 'Headless', help: 'Requests your rules cover go through. Everything else is refused, never queued.' },
  bypass: { label: 'Bypass in a sandbox', help: 'Not available yet.' },
};

export const modeLabel = (mode: string) => MODE_TEXT[mode]?.label ?? mode;

/** Permission writes either apply immediately or create a request for the owner to approve. */
export const isApprovalRequest = (value: object | void): value is Action =>
  !!value && 'requested_by' in value && 'state' in value;

/** One OneMind client per token, as the other Settings pages build it. */
export function usePermSdk(): OneMind {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

/** The SDK's error as the dashboard's ApiError, so usePoll and the toasts read it. */
export function asApiError(e: unknown): ApiError {
  if (e instanceof ApiError) return e;
  if (e instanceof OneMindError) return new ApiError(e.status, e.code as ApiError['code'], e.message.replace(/^HTTP \d+ [a-z_]+: /, ''), e.reason);
  return new ApiError(0, 'unknown', e instanceof Error ? e.message : String(e));
}

export async function read<T>(job: Promise<T>): Promise<T> {
  try {
    return await job;
  } catch (e) {
    throw asApiError(e);
  }
}

/** What went wrong, in words a first-time owner can act on. */
export function explain(e: unknown): string {
  const err = asApiError(e);
  switch (err.reason) {
    case 'no_owner_passkey':
      return 'Add a passkey first (Settings, Account). Nothing can be loosened before the owner has one.';
    case 'owner_exempt':
      return 'The owner’s own requests run directly and have no mode.';
    case 'step_up_required':
      return 'This needs a fresh passkey sign-in, and it was not completed.';
    case 'needs_proven_key':
      return 'This needs a proven hardware key, which is not available yet. Approve the request once instead.';
    case 'mode_ignores_rules':
      return 'This requester is on Locked or Always ask, which ignore rules. Change its mode first.';
    case 'passkey_other_account':
      return err.message;
    case 'bypass_not_built':
      return 'Bypass in a sandbox is not available yet.';
  }
  if (err.code === 'permission_denied') return 'You are not allowed to change this. Ask the owner.';
  return err.message || 'Something went wrong.';
}

/**
 * `run(fn)` sends a change; if the gateway wants a fresh passkey, it signs in with one (the same
 * ceremony as the sign-in page), switches this tab to that session and sends the change once more.
 */
export function useStepUp() {
  const { anon, signIn, principal } = useSignedIn();
  return useCallback(async <T,>(fn: (sdk: OneMind) => Promise<T>, sdk: OneMind): Promise<T> => {
    try {
      return await fn(sdk);
    } catch (e) {
      if (!(e instanceof OneMindError) || e.reason !== 'step_up_required') throw asApiError(e);
      if (!webauthnSupported()) throw new ApiError(401, 'unauthenticated', 'This needs a passkey, and this browser cannot use one. Use a browser with your passkey.', 'step_up_required');
      const options = await anon.loginOptions();
      const result = await anon.loginPasskey(await getPasskey(options.publicKey));
      const fresh = new OneMind({ baseUrl: window.location.origin, token: result.access_token, retries: 1 });
      if (principal?.id && result.principal?.id !== principal.id) {
        // Someone else's passkey: never switch this tab to another person's session.
        void fresh.call({ method: 'POST', path: '/v1/auth/logout', body: {} }).catch(() => undefined);
        throw new ApiError(403, 'permission_denied', 'That passkey belongs to another account. Use your own passkey.', 'passkey_other_account');
      }
      // The earlier session is not logged out here: polls still in flight with its token would get a 401
      // and sign the person out. It is forgotten by this tab and ends at its expiry (Account, Signed-in devices).
      await signIn(result.access_token);
      try {
        return await fn(fresh);
      } catch (again) {
        throw asApiError(again);
      }
    }
  }, [anon, signIn, principal]);
}

/** "agent:notes" for an agent id the agents list returns ("notes" or "agent:notes"). */
export const agentKey = (id: string) => (id.startsWith('agent:') ? id : `agent:${id}`);
