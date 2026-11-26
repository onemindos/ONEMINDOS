// SPDX-License-Identifier: Apache-2.0
// The step-up an owner change names (D-028, design 3.11): made in place, then the change is sent once more.
import { describe, expect, it } from "vitest";
import { OneMind, OneMindError, STEP_UP_HEADER, stepUpOf } from "../src/index.js";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
const STEP = { op: "users.create", target: "", body: { display_name: "Bea", role: "adult", username: null }, required_level: "L2" };
const refusal = () => json(401, { error: "unauthenticated", message: "needs your proven key", reason: "step_up_required", details: [{ step_up: STEP }] });

function hub(opts: { stepUp?: (pk: Record<string, unknown>) => Promise<Record<string, unknown>>; answer?: () => Response } = {}) {
  const calls: { path: string; method: string; headers: Record<string, string>; body: unknown }[] = [];
  const om = new OneMind({
    baseUrl: "http://localhost:8080", token: "t", sleep: async () => {}, ...(opts.stepUp ? { stepUp: opts.stepUp } : {}),
    fetch: (async (url: string, init: RequestInit) => {
      const path = new URL(url).pathname;
      const headers = init.headers as Record<string, string>;
      calls.push({ path, method: String(init.method), headers, body: init.body ? JSON.parse(String(init.body)) : undefined });
      if (path === "/v1/auth/step-up/options") return json(200, { challenge_id: "c", required_level: "L2", grace: false, publicKey: { challenge: "abc" } });
      if (path === "/v1/auth/step-up") return json(200, { step_up: "grant-1", expires_at: "t", level: "L2" });
      if (headers[STEP_UP_HEADER] === "grant-1") return json(201, { id: "usr_1" });
      return (opts.answer ?? refusal)();
    }) as typeof fetch,
  });
  return { om, calls };
}

describe("step-up in place", () => {
  it("confirms with the passkey and sends the change once more with the grant", async () => {
    const signed: unknown[] = [];
    const { om, calls } = hub({ stepUp: async (pk) => { signed.push(pk); return { id: "cred" }; } });
    const out = await om.call<{ id: string }>({ method: "POST", path: "/v1/users", body: { display_name: "Bea", role: "adult" } });
    expect(out.id).toBe("usr_1");
    expect(calls.map((c) => c.path)).toEqual(["/v1/users", "/v1/auth/step-up/options", "/v1/auth/step-up", "/v1/users"]);
    // The hub's own echo of the body is what gets bound, never a client rebuild of it.
    expect(calls[1]!.body).toEqual({ op: STEP.op, target: STEP.target, body: STEP.body });
    expect(signed).toEqual([{ challenge: "abc" }]);
    expect(calls[2]!.body).toEqual({ credential: { id: "cred" } });
    expect(calls[3]!.headers[STEP_UP_HEADER]).toBe("grant-1");
  });

  it("without a signer the refusal reaches the caller with the step-up readable", async () => {
    const { om, calls } = hub();
    const e = await om.call({ method: "POST", path: "/v1/users", body: {} }).catch((x: unknown) => x);
    expect(e).toBeInstanceOf(OneMindError);
    expect(stepUpOf(e)).toEqual(STEP);
    expect(calls).toHaveLength(1);
  });

  it("tries once only: a second refusal after the grant is the caller's", async () => {
    let n = 0;
    const { om, calls } = hub({ stepUp: async () => ({ id: "cred" }), answer: () => { n++; return refusal(); } });
    // The request already carries a grant and the hub still refuses it (say the body changed): no loop.
    const e = await om.call({ method: "PUT", path: "/v1/apps/x/access", body: {}, headers: { [STEP_UP_HEADER]: "old" } }).catch((x: unknown) => x);
    expect(stepUpOf(e)).toBeDefined();
    expect(calls).toHaveLength(1);
    expect(n).toBe(1);
  });

  it("a refusal without details, or not a step-up, is never answered with a passkey", async () => {
    const signer = async () => { throw new Error("must not be asked"); };
    for (const answer of [
      () => json(401, { error: "unauthenticated", message: "sign in again", reason: "step_up_required" }),
      () => json(409, { error: "conflict", message: "needs your proven key", reason: "verification_level_unmet" }),
    ]) {
      const { om } = hub({ stepUp: signer, answer });
      const e = await om.call({ method: "POST", path: "/v1/users", body: {} }).catch((x: unknown) => x);
      expect(e).toBeInstanceOf(OneMindError);
      expect(stepUpOf(e)).toBeUndefined();
    }
  });
});
