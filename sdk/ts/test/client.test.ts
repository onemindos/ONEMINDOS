// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it } from "vitest";
import {
  AmbiguousResultError, ExpiredError, NetworkError, NotFoundError, OneMind, OneMindError, normalizeHubUrl,
  needsUpdate, PROTOCOL_HEADER, PROTOCOL_MAX_HEADER, PROTOCOL_MIN_HEADER, PROTOCOL_VERSION, protocolRange,
  UnexpectedResponseError, UpgradeRequiredError, type OneMindEvent,
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

describe("actions.request", () => {
  it("reuses expires_at for one idempotency key even when the hub clock moves on", async () => {
    let tick = 0;
    const bodies: { idempotency_key: string; expires_at: string }[] = [];
    const { om } = client((url, init) => {
      const headers = { date: new Date(Date.now() + 5000 * ++tick).toUTCString() };
      if (url.endsWith("/v1/instance")) return json(200, { name: "x", version: "0", hub_node_id: null }, headers);
      bodies.push(JSON.parse(String(init.body)));
      return json(201, action("awaiting_approval"), headers);
    });
    await om.actions.request({ type: "app.install", appId: "x", idempotencyKey: "k1" });
    await om.actions.request({ type: "app.install", appId: "x", idempotencyKey: "k1" });
    await om.actions.request({ type: "app.install", appId: "x", idempotencyKey: "k2" });
    await om.actions.request({ type: "app.install", appId: "x" });
    await om.actions.request({ type: "app.install", appId: "x" });
    expect(bodies[0]!.expires_at).toBe(bodies[1]!.expires_at);
    expect(bodies[2]!.expires_at).not.toBe(bodies[0]!.expires_at);
    expect(bodies[3]!.idempotency_key).not.toBe(bodies[4]!.idempotency_key);
  });
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

describe("fromEnv with ONEMIND_GATEWAY_CA", () => {
  const impl = (om: OneMind) => (om as unknown as { fetchImpl: unknown }).fetchImpl;
  it("uses the caller's fetch over the CA fetch", () => {
    const f = (async () => new Response("[]")) as typeof fetch;
    expect(impl(OneMind.fromEnv({ ONEMIND_GATEWAY_URL: "https://gw:8443", ONEMIND_GATEWAY_CA: "PEM" }, { fetch: f }))).toBe(f);
  });
  it("installs a CA fetch only when the variable is non-empty", () => {
    const caOn = impl(OneMind.fromEnv({ ONEMIND_GATEWAY_URL: "https://gw:8443", ONEMIND_GATEWAY_CA: "PEM" }));
    const empty = impl(OneMind.fromEnv({ ONEMIND_GATEWAY_URL: "https://gw:8443", ONEMIND_GATEWAY_CA: " " }));
    const unset = impl(OneMind.fromEnv({ ONEMIND_GATEWAY_URL: "https://gw:8443" }));
    expect(caOn).not.toBe(unset);
    expect(caOn).not.toBe(empty);
  });
});

describe("me.home (UMB-P07)", () => {
  const home = { version: 3, layout: "desktop", appearance: { theme: "dark" }, dock: [], grid: { order: [], hidden: [] }, widgets: [], seen: {}, updated_at: null };

  it("reads the document with its ETag and saves with If-Match", async () => {
    const { om, calls } = client((url, init) =>
      init.method === "PUT" ? json(200, { ...home, updated_at: "t" }, { etag: '"b"' }) : json(200, home, { etag: '"a"' }));
    const got = await om.me.home.get();
    expect(got.etag).toBe('"a"');
    const saved = await om.me.home.save(got.home as never, got.etag);
    expect(saved.etag).toBe('"b"');
    const put = calls[1]!;
    expect(put.url).toBe("http://localhost:8080/v1/me/home");
    expect((put.init.headers as Record<string, string>)["If-Match"]).toBe('"a"');
  });

  it("a stale ETag is a typed error, not a retry", async () => {
    const { om, calls } = client(() => json(412, { error: "stale_precondition", message: "Home changed elsewhere", reason: "etag_mismatch" }));
    await expect(om.me.home.save(home as never, '"old"')).rejects.toBeInstanceOf(OneMindError);
    expect(calls).toHaveLength(1);
  });
});

describe("notifications.preferences (#841)", () => {
  const doc = { quiet_hours: null, routes: [], digest: { enabled: false, at: "08:00" } };

  it("reads the document with its ETag and saves with If-Match", async () => {
    const { om, calls } = client((_url, init) => init.method === "PUT" ? json(200, doc, { etag: '"b"' }) : json(200, doc, { etag: '"a"' }));
    const got = await om.notifications.preferences.get();
    expect(got.etag).toBe('"a"');
    const saved = await om.notifications.preferences.save(got.prefs, got.etag);
    expect(saved.etag).toBe('"b"');
    expect(calls[1]!.url).toBe("http://localhost:8080/v1/notifications/preferences");
    expect((calls[1]!.init.headers as Record<string, string>)["If-Match"]).toBe('"a"');
  });

  it("a stale ETag is a typed error and is not retried", async () => {
    const { om, calls } = client(() => json(409, { error: "conflict", message: "preferences changed since you read them (ETag mismatch)" }));
    await expect(om.notifications.preferences.save(doc, '"old"')).rejects.toBeInstanceOf(OneMindError);
    expect(calls).toHaveLength(1);
  });
});

describe("network.view", () => {
  it("reads GET /v1/network", async () => {
    const view = { available: true, interfaces: [], gateways: [], dns: ["192.0.2.53"], ports: [], dropped: 0 };
    const { om, calls } = client(() => json(200, view));
    expect((await om.network.view()).dns).toEqual(["192.0.2.53"]);
    expect(calls[0]!.url).toBe("http://localhost:8080/v1/network");
    expect(calls[0]!.init.method).toBe("GET");
  });
  it("reads GET /v1/network/firewall", async () => {
    const view = { available: true, exposure: "lan_and_mesh_only", open_to_anywhere: [], rules: [], chains: [], sets: [], other_tables: [], editable: false, dropped: 0 };
    const { om, calls } = client(() => json(200, view));
    expect((await om.network.firewall()).exposure).toBe("lan_and_mesh_only");
    expect(calls[0]!.url).toBe("http://localhost:8080/v1/network/firewall");
    expect(calls[0]!.init.method).toBe("GET");
  });
  it("asks to open a port, confirms it and removes it (P-09 part 2)", async () => {
    const { om, calls } = client((_url, init) => json(init.method === "DELETE" ? 200 : 202, { id: "act-1", state: "awaiting_approval", removed: true }));
    expect((await om.network.allow({ proto: "tcp", port: 8123, scope: "lan" })).id).toBe("act-1");
    expect(calls[0]!.url).toBe("http://localhost:8080/v1/network/firewall/allow");
    expect(calls[0]!.init.method).toBe("POST");
    expect(JSON.parse(String(calls[0]!.init.body))).toEqual({ proto: "tcp", port: 8123, scope: "lan" });
    await om.network.confirmAllow("act 1");
    expect(calls[1]!.url).toBe("http://localhost:8080/v1/network/firewall/allow/act%201/confirm");
    expect(calls[1]!.init.method).toBe("POST");
    await om.network.removeAllow("act-1");
    expect(calls[2]!.url).toBe("http://localhost:8080/v1/network/firewall/allow/act-1");
    expect(calls[2]!.init.method).toBe("DELETE");
  });
});

describe("protocol generation (sdk/contracts/protocol-versions.md)", () => {
  it("declares its generation on every request", async () => {
    const { om, calls } = client(() => json(200, { name: "x", version: "0", hub_node_id: null }));
    await om.instance.get();
    expect((calls[0]!.init.headers as Record<string, string>)[PROTOCOL_HEADER]).toBe(String(PROTOCOL_VERSION));
  });

  it("turns upgrade_required into UpgradeRequiredError without retrying", async () => {
    const body = { error: "upgrade_required", reason: "protocol_too_old", message: "Update the app." };
    const { om, calls } = client(() => json(400, body, { [PROTOCOL_MIN_HEADER]: "9", [PROTOCOL_MAX_HEADER]: "9" }));
    const err = await om.instance.get().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(UpgradeRequiredError);
    expect((err as UpgradeRequiredError).reason).toBe("protocol_too_old");
    expect(calls).toHaveLength(1);
  });

  it("reads the hub's range from any answer", () => {
    const h = (min?: string, max?: string) => new Headers({ ...(min ? { [PROTOCOL_MIN_HEADER]: min } : {}), ...(max ? { [PROTOCOL_MAX_HEADER]: max } : {}) });
    expect(protocolRange(h("1", "2"))).toEqual({ min: 1, max: 2 });
    expect(protocolRange(h())).toBeUndefined(); // a hub from before the headers: nothing to say
    expect(protocolRange(h("3", "2"))).toBeUndefined();
    expect(needsUpdate(h(String(PROTOCOL_VERSION + 1), String(PROTOCOL_VERSION + 1)))).toBe(true);
    expect(needsUpdate(h("1", String(PROTOCOL_VERSION)))).toBe(false);
  });

  it("speaks a generation the committed OpenAPI contract serves", async () => {
    // node:fs without Node types (tsconfig "types": []), as gateway-ca.test.ts does.
    const fs: any = await import(/* @vite-ignore */ "node:" + "fs");
    const spec = JSON.parse(fs.readFileSync(new URL("../../openapi/onemind-v1.json", import.meta.url), "utf8"));
    const proto = spec.info["x-onemind-protocol"];
    expect(proto.header).toBe(PROTOCOL_HEADER);
    expect(PROTOCOL_VERSION).toBeLessThanOrEqual(proto.current);
    expect(PROTOCOL_VERSION).toBeGreaterThanOrEqual(proto.current - 1);
  });
});

describe("domains hosts and tips.whatsNew", () => {
  it("sends the typed confirmation, escapes names, and refuses redirects for what's new", async () => {
    const { om, calls } = client((url, init) => {
      if (url.endsWith("/whats-new")) return json(200, { os_version: "0.1.2", entries: [] });
      if (init.method === "DELETE") return new Response(null, { status: 204 });
      return json(200, { hostname: "ntfy.example.org", app_id: "ntfy", state: "approved" });
    });
    await om.domains.requestHost("example.org", "ntfy");
    await om.domains.approveHost("ntfy.example.org", "ntfy.example.org");
    await om.domains.removeHost("ntfy.example.org");
    expect((await om.tips.whatsNew()).os_version).toBe("0.1.2");
    expect(calls.map((c) => `${c.init.method} ${c.url.replace("http://localhost:8080", "")}`)).toEqual([
      "POST /v1/domains/example.org/hosts",
      "POST /v1/domains/hosts/ntfy.example.org/approve",
      "DELETE /v1/domains/hosts/ntfy.example.org",
      "GET /v1/tips/whats-new",
    ]);
    expect(JSON.parse(String(calls[1]!.init.body))).toEqual({ confirm: "ntfy.example.org" });
    expect(calls[3]!.init.redirect).toBe("error");
  });
});

describe("call with DELETE (P-06)", () => {
  it("sends the verb and the token, never retries a DELETE, and returns the filed action", async () => {
    const { om, calls } = client(() => json(202, { id: "a9", type: "ssh.key.remove", state: "awaiting_approval" }));
    const got = await om.call<{ id: string }>({ method: "DELETE", path: "/v1/ssh/keys/abc-_def" });
    expect(got.id).toBe("a9");
    expect(calls[0]!.init.method).toBe("DELETE");
    expect(calls[0]!.url).toBe("http://localhost:8080/v1/ssh/keys/abc-_def");
    const { om: down, calls: n } = client(() => json(503, { error: "unavailable", message: "later" }));
    await expect(down.call({ method: "DELETE", path: "/v1/ssh/keys/x" })).rejects.toBeInstanceOf(OneMindError);
    expect(n).toHaveLength(1);
  });
});
