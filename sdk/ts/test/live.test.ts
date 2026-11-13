// SPDX-License-Identifier: Apache-2.0
// Conformance against a real gateway. core/tests/test_sdk_conformance.py starts one and runs this
// file with ONEMIND_CONFORMANCE_HUB, _OWNER and _AGENT set; otherwise it is skipped.
import { describe, expect, it } from "vitest";
import { OneMind, PermissionDeniedError, type OneMindEvent } from "../src/index.js";

const env = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const hub = env.ONEMIND_CONFORMANCE_HUB;

describe.skipIf(!hub)("live gateway", () => {
  const owner = new OneMind({ baseUrl: hub ?? "http://x", token: env.ONEMIND_CONFORMANCE_OWNER, principal: "owner" });
  const agent = new OneMind({ baseUrl: hub ?? "http://x", token: env.ONEMIND_CONFORMANCE_AGENT });

  it("reads, requests, refuses the agent's approve, approves, streams and verifies", async () => {
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
    // One fixed expiry: the hub compares it, to the second, when a key is replayed. (Computing it
    // per call straddled a second boundary and made this test flaky: HTTP 409 on the replay.)
    const expiresAt = new Date(Date.now() + 3600_000).toISOString().replace(/\.\d{3}Z$/, "Z");
    const a = await agent.actions.request({ type: "app.install", appId: "whoami", idempotencyKey: "ts-conformance", expiresAt });
    expect(a.state).toBe("awaiting_approval");
    const again = await agent.actions.request({ type: "app.install", appId: "whoami", idempotencyKey: "ts-conformance", expiresAt });
    expect(again.id).toBe(a.id);
    await expect(agent.actions.approve(a.id)).rejects.toBeInstanceOf(PermissionDeniedError);
    const done = await owner.actions.approve(a.id);
    expect(done.decided_by?.id).toBe("owner");
    await sub;
    expect(seen[0]?.type).toBe("action.requested");
    expect((await owner.audit.verify()).ok).toBe(true);
  }, 20_000);
});
