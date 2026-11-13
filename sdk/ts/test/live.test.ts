// SPDX-License-Identifier: Apache-2.0
// Conformance against a real gateway. core/tests/test_sdk_conformance.py starts one and runs this
// file with ONEMIND_CONFORMANCE_HUB, _OWNER and _AGENT set; otherwise it is skipped.
import { describe, expect, it } from "vitest";
import { OneMind, PermissionDeniedError, type OneMindEvent } from "../src/index.js";

const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const hub = env.ONEMIND_CONFORMANCE_HUB;

describe.skipIf(!hub)("live gateway", () => {
  const owner = new OneMind({ baseUrl: hub ?? "http://x", token: env.ONEMIND_CONFORMANCE_OWNER, principal: "owner" });

  it("reads, requests, refuses the agent's approve, approves, streams and verifies", async () => {
    const payloads: string[] = [];
    const requestSeconds: number[] = [];
    const statuses: number[] = [];
    let firstId = "";
    const agent = new OneMind({
      baseUrl: hub ?? "http://x", token: env.ONEMIND_CONFORMANCE_AGENT, retries: 2,
      fetch: async (input, init) => {
        const response = await fetch(input, init);
        if (init?.method === "POST" && new URL(String(input)).pathname === "/v1/actions") {
          payloads.push(String(init.body));
          requestSeconds.push(Math.floor(Date.now() / 1000));
          statuses.push(response.status);
          if (payloads.length === 1) {
            firstId = ((await response.clone().json()) as { id: string }).id;
            await response.arrayBuffer();
            // Lose the response AFTER the hub accepted it, then cross a whole second.
            // A retry must replay this logical call, not recalculate its absolute expiry.
            await new Promise((resolve) => setTimeout(resolve, 1100));
            throw new TypeError("simulated lost response");
          }
        }
        return response;
      },
    });
    expect(await owner.healthz()).toBe(true);
    expect((await owner.instance.get()).name).toBeTruthy();
    expect((await owner.apps.list()).some((a) => a.id === "whoami")).toBe(true);
    expect(Array.isArray(await owner.nodes.list())).toBe(true);
    const ctrl = new AbortController();
    const seen: OneMindEvent[] = [];
    const head = (await owner.audit.list({ limit: 500 })).records.at(-1)?.seq ?? 0;
    const sub = owner.events.subscribe({ types: ["action.*"], sinceId: String(head), signal: ctrl.signal }, (e) => {
      seen.push(e);
      if (seen.some((x) => x.data?.to === "succeeded")) ctrl.abort();
    });
    const a = await agent.actions.request({ type: "app.install", appId: "whoami", idempotencyKey: "ts-conformance" });
    expect(a.state).toBe("awaiting_approval");
    expect(payloads).toHaveLength(2);
    expect(statuses).toEqual([201, 200]);
    expect(requestSeconds[1]).toBeGreaterThan(requestSeconds[0]!);
    expect(payloads[1]).toBe(payloads[0]);
    expect(a.id).toBe(firstId);
    const changed = JSON.parse(payloads[0]!) as { expires_at: string };
    changed.expires_at = new Date(Date.parse(changed.expires_at) + 1000).toISOString();
    const conflict = await fetch(`${hub}/v1/actions`, {
      method: "POST", headers: { Authorization: `Bearer ${env.ONEMIND_CONFORMANCE_AGENT}`, "Content-Type": "application/json" },
      body: JSON.stringify(changed),
    });
    expect(conflict.status).toBe(409);
    expect((await conflict.json() as { error: string }).error).toBe("conflict");
    expect((await owner.actions.list()).filter((x) => x.id === a.id)).toHaveLength(1);
    // A replay in a later second must still be the same request: the SDK keeps expires_at per key.
    await new Promise((r) => setTimeout(r, 1200));
    const again = await agent.actions.request({ type: "app.install", appId: "whoami", idempotencyKey: "ts-conformance" });
    expect(again.id).toBe(a.id);
    await expect(agent.actions.approve(a.id)).rejects.toBeInstanceOf(PermissionDeniedError);
    const done = await owner.actions.approve(a.id);
    expect(done.decided_by?.id).toBe("owner");
    expect(done.state).toBe("succeeded");
    await sub;
    expect(seen[0]?.type).toBe("action.requested");
    const records = (await owner.audit.list({ actionId: a.id })).records;
    expect(records.filter((r) => r.event === "action.requested")).toHaveLength(1);
    expect(records.filter((r) => r.event === "action.dispatched")).toHaveLength(1);
    expect((await owner.audit.verify()).ok).toBe(true);
  }, 20_000);
});
