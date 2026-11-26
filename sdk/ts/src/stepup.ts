// SPDX-License-Identifier: Apache-2.0
// The step-up an owner change asks for (D-028; gateway permissions design 3.11). Once the household holds a
// proven key, changes such as adding a person, sharing an app or a standing approval answer
// 401 step_up_required with `details: [{step_up: {op, target, body, required_level}}]`. A client then asks
// for a passkey challenge bound to exactly that change, has a key at that level answer it, and repeats the
// request once with the single-use grant in the OneMind-Step-Up header. The body is echoed by the hub, so
// no client ever rebuilds what the hub hashes.
import { OneMindError } from "./errors.js";

export const STEP_UP_HEADER = "OneMind-Step-Up";

export interface StepUpRequest {
  op: string;
  target: string;
  body: Record<string, unknown>;
  /** "L1" (a fresh passkey) or "L2"/"L3" (a proven key; a synced phone passkey can't answer). */
  required_level: string;
}

/** Asks the person's authenticator to answer a WebAuthn request (the hub's `publicKey` JSON). */
export type PasskeySigner = (publicKey: Record<string, unknown>) => Promise<Record<string, unknown>>;

/** The step-up a refusal names, or undefined when it is not one a client can make in place. */
export function stepUpOf(e: unknown): StepUpRequest | undefined {
  if (!(e instanceof OneMindError) || e.status !== 401 || e.reason !== "step_up_required") return undefined;
  for (const d of e.details ?? []) {
    const s = (d as { step_up?: unknown }).step_up as Partial<StepUpRequest> | undefined;
    if (s && typeof s.op === "string" && typeof s.target === "string" && s.body && typeof s.body === "object"
        && !Array.isArray(s.body) && typeof s.required_level === "string") return s as StepUpRequest;
  }
  return undefined;
}

/** What `call` needs to make the two step-up requests; OneMind implements it. */
export interface StepUpTransport {
  call<T>(r: { method: "POST"; path: string; body: unknown; retry: false }): Promise<T>;
}

/** options -> the authenticator -> verify: returns the grant to send once as OneMind-Step-Up. */
export async function completeStepUp(client: StepUpTransport, s: StepUpRequest, sign: PasskeySigner): Promise<string> {
  const opts = await client.call<{ publicKey: Record<string, unknown> }>({
    method: "POST", path: "/v1/auth/step-up/options", body: { op: s.op, target: s.target, body: s.body }, retry: false,
  });
  const credential = await sign(opts.publicKey);
  // A consumed authenticator assertion must never be resent automatically: retry stays off.
  const g = await client.call<{ step_up: string }>({ method: "POST", path: "/v1/auth/step-up", body: { credential }, retry: false });
  if (!g || typeof g.step_up !== "string" || !g.step_up) throw new OneMindError(200, "unexpected_response", "the hub answered the step-up without a grant");
  return g.step_up;
}
