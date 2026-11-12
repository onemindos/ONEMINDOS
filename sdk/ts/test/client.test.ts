// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  AmbiguousResultError, ExpiredError, NetworkError, NotFoundError, OneMind, OneMindError, normalizeHubUrl,
  UnexpectedResponseError, type OneMindEvent,
} from "../src/index.js";

const TOKEN = "test-token-0123456789abcdef";
type Handler = (url: string, init: RequestInit) => Response | Promise<Response>;

function client(h: Handler, extra: Partial<ConstructorParameters<typeof OneMind>[0]> = {}) {
  const calls: { url: string; init: RequestInit }[] = [];
  const om = new OneMind({
    baseUrl: "http://localhost:8080/",
    token: TOKEN,
    sleep: async () => {},
    fetch: (async (url: string, init: RequestInit) => {
      calls.push({ url, init });
      return h(url, init);
    }) as typeof fetch,
    ...extra,
  });
  return { om, calls };
}

const json = (status: number, body: unknown, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json", ...headers } });

const action = (state: string, decidedBy?: string) => ({
  id: "a1", type: "app.install", params: { app_id: "x" }, state, idempotency_key: "k",
  requested_by: { id: "hermes", kind: "agent", role: "agent" }, created_at: "t", updated_at: "t", expires_at: "t",
  decided_by: decidedBy ? { id: decidedBy, kind: "person", role: "owner" } : null, decided_at: null, result: null, version: 2,
});

describe("transport", () => {
  it("retries GET on 503 and maps typed errors", async () => {
    let n = 0;
    const { om, calls } = client((url) => {
      if (url.endsWith("/v1/nodes")) return ++n < 3 ? new Response("", { status: 503 }) : json(200, [{ node_id: "a" }]);
      if (url.endsWith("/v1/nodes/x")) return json(404, { error: "not_found", message: "no such node" });
      if (url.endsWith("/v1/instance")) return new Response("<html>", { status: 200 });
      return json(418, { error: "brand_new", message: "newer gateway" });
    });
    expect(await om.nodes.list()).toEqual([{ node_id: "a" }]);
    expect(n).toBe(3);
    expect((calls[0]!.init.headers as Record<string, string>).Authorization).toBe(`Bearer ${TOKEN}`);
    await expect(om.nodes.get("x")).rejects.toBeInstanceOf(NotFoundError);
    await expect(om.instance.get()).rejects.toBeInstanceOf(UnexpectedResponseError);
    const e = await om.apps.list().catch((x) => x);
    expect(e).toBeInstanceOf(OneMindError);
    expect(e.code).toBe("brand_new");
  });

  it("never prints the token", async () => {
    const { om } = client(() => {
      throw new TypeError(`connect failed ${TOKEN}`);
    }, { retries: 1 });
    expect(String(om)).toBe("OneMind(hub=http://localhost:8080, principal=?)");
    const e = await om.healthz().catch((x) => x);
    expect(e).toBeInstanceOf(NetworkError);
    expect(String(e)).not.toContain(TOKEN);
  });

  it("warns once for plain http to a non-local hub", async () => {
    const warnings: string[] = [];
    const { om } = client(() => json(200, { ok: true }), { baseUrl: "hub.example:8080", onWarning: (m) => warnings.push(m) });
    await om.healthz();
    await om.healthz();
    expect(om.baseUrl).toBe("http://hub.example:8080");
    expect(warnings).toHaveLength(1);
    expect(normalizeHubUrl("https://hub.local/")).toBe("https://hub.local");
    expect(() => normalizeHubUrl("ftp://x")).toThrow();
  });
});

describe("actions", () => {
  it("reuses one idempotency key across retries and uses the hub clock", async () => {
    const keys: string[] = [];
    const hubAhead = new Date(Date.now() + 3600_000).toUTCString();
    const { om } = client((url, init) => {
      if (url.endsWith("/v1/instance")) return json(200, { name: "x", version: "0", hub_node_id: null }, { date: hubAhead });
      const b = JSON.parse(String(init.body));
      keys.push(b.idempotency_key);
      if (keys.length === 1) return new Response("", { status: 502 });
      expect(Date.parse(b.expires_at) - Date.now()).toBeGreaterThan(24 * 3600_000 + 50 * 60_000);
      return json(201, { ...action("awaiting_approval"), idempotency_key: b.idempotency_key });
    });
    const a = await om.actions.request({ type: "app.install", appId: "ntfy" });
    expect(a.state).toBe("awaiting_approval");
    expect(keys).toHaveLength(2);
    expect(keys[0]).toBe(keys[1]);
  });

  it("approve is never retried blindly and is confirmed only by read-back", async () => {
    for (const [principal, decidedBy, ok] of [["owner", "owner", true], ["owner", "other", false], [undefined, "owner", false]] as const) {
      let posts = 0;
      const { om } = client((_u, init) => {
        if (init.method === "POST") {
          posts++;
          return new Response("", { status: 502 });
        }
        return json(200, action("succeeded", decidedBy));
      }, { principal });
      const res = await om.actions.approve("a1").catch((x) => x);
      expect(posts).toBe(1);
      if (ok) expect(res.state).toBe("succeeded");
      else {
        expect(res).toBeInstanceOf(AmbiguousResultError);
        expect(res.action.state).toBe("succeeded");
      }
    }
    const { om } = client(() => json(409, { error: "expired", message: "too late" }));
    await expect(om.actions.deny("a1")).rejects.toBeInstanceOf(ExpiredError);
  });

  it("wait polls until terminal", async () => {
    const states = ["awaiting_approval", "accepted", "succeeded"];
    let i = 0;
    const { om } = client(() => json(200, action(states[Math.min(i++, 2)]!, "owner")));
    const seen: string[] = [];
    const a = await om.actions.wait("a1", { onChange: (x) => seen.push(x.state) });
    expect(a.state).toBe("succeeded");
    expect(seen).toEqual(states);
  });
});

describe("events", () => {
  it("parses SSE, resumes with Last-Event-ID and stops when the handler throws", async () => {
    const seenLast: string[] = [];
    let conn = 0;
    const transport = async function* (_url: string, headers: Record<string, string>) {
      seenLast.push(headers["Last-Event-ID"] ?? "");
      conn++;
      if (conn === 1) {
        yield "retry: 10\n\n: keepalive\n\nid: 7\nevent: action.requested\ndata: {\"id\":\"7\",\"type\":\"action.requested\",\"subject\":{\"action_id\":\"a1\"}}\n";
        yield "\n";
        return;
      }
      yield "id: 8\r\nevent: action.state_changed\r\ndata: {\"id\":\"8\",\"type\":\"action.state_changed\",\"data\":{\"to\":\"accepted\"}}\r\n\r\n";
    };
    const { om } = client(() => json(200, {}));
    const got: OneMindEvent[] = [];
    const stop = new Error("enough");
    const err = await om.events
      .subscribe({ types: ["action.*"], transport }, (e) => {
        got.push(e);
        if (got.length === 2) throw stop;
      })
      .catch((x) => x);
    expect(err).toBe(stop);
    expect(got.map((e) => e.id)).toEqual(["7", "8"]);
    expect(seenLast).toEqual(["", "7"]);
  });

  it("reads a real fetch stream and rejects on 404", async () => {
    const body = new ReadableStream<Uint8Array>({
      start(c) {
        c.enqueue(new TextEncoder().encode("id: 1\nevent: audit.appended\ndata: {\"id\":\"1\",\"type\":\"audit.appended\"}\n\n"));
        c.close();
      },
    });
    let n = 0;
    const { om } = client(() => (n++ === 0 ? new Response(body, { status: 200 }) : json(404, { error: "not_found", message: "x" })));
    const got: string[] = [];
    await expect(om.events.subscribe({}, (e) => void got.push(e.type))).rejects.toBeInstanceOf(NotFoundError);
    expect(got).toEqual(["audit.appended"]);
  });
});

describe("fromEnv", () => {
  it("prefers the CLI names, then the agent Secret", () => {
    expect(OneMind.fromEnv({ ONEMIND_GATEWAY_URL: "http://gw:8080", ONEMIND_AGENT_TOKEN: "t" }).baseUrl).toBe("http://gw:8080");
    expect(() => OneMind.fromEnv({})).toThrow();
  });
});
