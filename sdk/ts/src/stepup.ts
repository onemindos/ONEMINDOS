// SPDX-License-Identifier: Apache-2.0
// The step-up an owner change asks for (D-028; gateway permissions design 3.11). Once the household holds a
// proven key, changes such as adding a person, sharing an app or a standing approval answer
// 401 step_up_required with `details: [{step_up: {op, target, body, required_level}}]`. A client then asks
// for a passkey challenge bound to exactly that change, has a key at that level answer it, and repeats the
// request once with the single-use grant in the OneMind-Step-Up header. The body is echoed by the hub, so
// no client ever rebuilds what the hub hashes.
//
// Confirming at the box (N-1 = b): before the household's first proven key, an L2 change is confirmed with
// any passkey plus a 6-digit code the box's own screen shows (`box: "required"`). The same path revokes a
// lost last proven key (`box: "alt"`, chosen with `atBox`). The code is never in an API answer: the person
// reads it at the box and types it, through the `boxCode` callback.
import { OneMindError } from "./errors.js";

export const STEP_UP_HEADER = "OneMind-Step-Up";

export interface StepUpRequest {
  op: string;
  target: string;
  body: Record<string, unknown>;
  /** "L1" (a fresh passkey) or "L2"/"L3" (a proven key; a synced phone passkey can't answer). */
  required_level: string;
  /** "required": a passkey plus the code on the box's screen; "alt": that, instead of the level, on request. */
  box?: "required" | "alt" | null;
}

/** Asks the person for the code the box's own screen shows now; `what` says what it confirms. */
export type BoxCodeAsker = (what: string) => Promise<string>;

export interface StepUpOptions {
  boxCode?: BoxCodeAsker;
  /** For `box: "alt"` (e.g. revoking a lost last proven key): confirm at the box instead of with that key. */
  atBox?: boolean;
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

/** options -> (the box's code) -> the authenticator -> verify: returns the grant to send once as OneMind-Step-Up. */
export async function completeStepUp(client: StepUpTransport, s: StepUpRequest, sign: PasskeySigner, o: StepUpOptions = {}): Promise<string> {
  const atBox = s.box === "alt" && !!o.atBox;
  // Fail before the hub shows a code nobody can type here (a CLI, an app without the prompt).
  if ((s.box === "required" || atBox) && !o.boxCode) throw boxCodeUnavailable();
  const opts = await client.call<{ publicKey: Record<string, unknown>; box_code_required?: boolean }>({
    method: "POST", path: "/v1/auth/step-up/options", body: { op: s.op, target: s.target, body: s.body, ...(atBox ? { at_box: true } : {}) }, retry: false,
  });
  let box_code: string | undefined;
  if (opts.box_code_required) {
    if (!o.boxCode) throw boxCodeUnavailable();
    box_code = (await o.boxCode(s.op)).replace(/\s+/g, "");
  }
  const credential = await sign(opts.publicKey);
  // A consumed authenticator assertion must never be resent automatically: retry stays off.
  const g = await client.call<{ step_up: string }>({ method: "POST", path: "/v1/auth/step-up", body: { credential, ...(box_code ? { box_code } : {}) }, retry: false });
  if (!g || typeof g.step_up !== "string" || !g.step_up) throw new OneMindError(200, "unexpected_response", "the hub answered the step-up without a grant");
  return g.step_up;
}

function boxCodeUnavailable(): OneMindError {
  return new OneMindError(409, "conflict", "this needs your passkey and the code on the box's own screen; do it in the dashboard, at the box", { reason: "box_code_required" });
}
