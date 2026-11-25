// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { OneMind, PROTOCOL_VERSION, type OneMindEvent } from "../src/index.js";

// Web Locks are not present in Node 22. Queue callbacks per name as the browser does.
const locks = new Map<string, Promise<unknown>>();
const request = vi.fn((name: string, options: { signal: AbortSignal }, run: () => Promise<void>) => {
  let cancel!: () => void;
  const cancelled = new Promise<never>((_, reject) => {
    cancel = () => reject(options.signal.reason);
    options.signal.addEventListener("abort", cancel, { once: true });
  });
  const queued = (locks.get(name) ?? Promise.resolve()).then(() => {
    options.signal.removeEventListener("abort", cancel);
    options.signal.throwIfAborted();
    return run();
  });
  locks.set(name, queued.catch(() => {}));
  return Promise.race([queued, cancelled]);
});

beforeEach(() => {
  locks.clear();
  request.mockClear();
  vi.stubGlobal("window", {});
  vi.stubGlobal("navigator", { locks: { request } });
});
afterEach(() => vi.unstubAllGlobals());

function gateway() {
  let connected = 0, peak = 0;
  const streams: { controller: ReadableStreamDefaultController<Uint8Array>; headers: Headers }[] = [];
  const fetch = vi.fn(async (_url: RequestInfo | URL, init?: RequestInit) => {
    const headers = new Headers(init?.headers);
    const body = new ReadableStream<Uint8Array>({
      start(controller) {
        connected++;
        peak = Math.max(peak, connected);
        streams.push({ controller, headers });
        init?.signal?.addEventListener("abort", () => {
          connected--;
          try { controller.close(); } catch { /* the transport has already failed */ }
        }, { once: true });
      },
    });
    return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
  });
  return { fetch, streams, get peak() { return peak; }, get connected() { return connected; } };
}

function send(stream: ReadableStreamDefaultController<Uint8Array>, event: OneMindEvent) {
  stream.enqueue(new TextEncoder().encode(`id: ${event.id}\ndata: ${JSON.stringify(event)}\n\n`));
}
const baseUrl = "https://hub.example";

it("serves ten windows from one SSE connection, filters locally and resumes after leadership changes", async () => {
  const hub = gateway();
  const tabs = Array.from({ length: 10 }, () => ({
    om: new OneMind({ baseUrl, token: "session-for-ten-tabs", fetch: hub.fetch }),
    ctrl: new AbortController(), seen: [] as string[],
  }));
  const watch = (tab: typeof tabs[number], i: number) => {
    const receive = (e: OneMindEvent) => { tab.seen.push(e.type); };
    const signal = tab.ctrl.signal;
    return i === 0 ? tab.om.events.subscribe({ signal }, receive)
      : tab.om.events.subscribeShared({ signal, kind: i === 1 ? "camera" : undefined,
          area: i === 2 ? "kitchen" : undefined, bbox: i === 3 ? [170, -10, -170, 10] : undefined }, receive);
  };
  const first = tabs[0]!;
  const done = [watch(first, 0)];
  try {
    await vi.waitFor(() => expect(hub.connected).toBe(1));
    done.push(...tabs.slice(1).map((tab, i) => watch(tab, i + 1)));
    await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(10));
    const initial = hub.streams[0]!.controller;
    send(initial, { type: "asset.position", id: "1", subject: { area_id: "kitchen" },
      data: { kind: "camera", position: { lat: 1, lon: 179 } } });
    send(initial, { type: "node.status", id: "2", subject: { area_id: "hall" } });
    await vi.waitFor(() => expect(tabs.at(-1)!.seen).toHaveLength(2));
    expect(tabs.slice(1, 4).map(tab => tab.seen)).toEqual(Array(3).fill(["asset.position"]));
    expect(hub.fetch).toHaveBeenCalledTimes(1);
    first.ctrl.abort();
    await done[0];
    await vi.waitFor(() => expect(hub.streams).toHaveLength(2));
    expect(hub.streams[1]!.headers.get("Last-Event-ID")).toBe("2");
    send(hub.streams[1]!.controller, { type: "stream.reset", id: "3" });
    await vi.waitFor(() => expect(tabs[1]!.seen.at(-1)).toBe("stream.reset"));
    expect(hub.peak).toBe(1);
  } finally {
    for (const tab of tabs) tab.ctrl.abort();
    await Promise.all(done);
  }
  expect(hub.connected).toBe(0);
});

it("reconnects after a transport failure with backoff and the last durable id", async () => {
  const hub = gateway();
  const ctrl = new AbortController();
  const sleep = vi.fn(async (_ms: number) => {});
  const om = new OneMind({ baseUrl, token: "session-with-reconnect", fetch: hub.fetch, sleep });
  const received = vi.fn();
  const done = om.events.subscribeShared({ signal: ctrl.signal }, received);
  try {
    await vi.waitFor(() => expect(hub.connected).toBe(1));
    send(hub.streams[0]!.controller, { type: "action.requested", id: "17" });
    await vi.waitFor(() => expect(received).toHaveBeenCalledTimes(1));
    hub.streams[0]!.controller.error(new Error("connection dropped"));
    await vi.waitFor(() => expect(hub.streams).toHaveLength(2));
    expect(sleep.mock.calls[0]![0]).toBeGreaterThanOrEqual(500);
    expect(hub.streams[1]!.headers.get("Last-Event-ID")).toBe("17");
    expect(hub.peak).toBe(1);
  } finally {
    ctrl.abort();
    await done;
  }
});

it("isolates hubs and bearer sessions and keeps credentials out of coordination messages", async () => {
  const channelNames: string[] = [];
  const messages: unknown[] = [];
  const BrowserChannel = BroadcastChannel;
  vi.stubGlobal("BroadcastChannel", class extends BrowserChannel {
    constructor(name: string) { super(name); channelNames.push(name); }
    override postMessage(value: unknown) { messages.push(value); super.postMessage(value); }
  });
  const hub = gateway();
  const ctrl = new AbortController();
  const tokens = ["session-one", "session-two", "session-one"];
  const seen = tokens.map(() => vi.fn());
  const done = tokens.map((token, i) => {
    const client = new OneMind({ baseUrl: i === 2 ? "https://second.example" : baseUrl, token, fetch: hub.fetch });
    return client.events.subscribe({ signal: ctrl.signal }, seen[i]!);
  });
  try {
    await vi.waitFor(() => expect(hub.connected).toBe(3));
    const sessionTwo = hub.streams.find(s => s.headers.get("Authorization") === "Bearer session-two")!;
    send(sessionTwo.controller, { type: "node.status", id: "4" });
    await vi.waitFor(() => expect(seen[1]).toHaveBeenCalledTimes(1));
    expect(seen[0]).not.toHaveBeenCalled();
    expect(seen[2]).not.toHaveBeenCalled();
    const lockNames = request.mock.calls.map(([name]) => name);
    expect(new Set(channelNames).size).toBe(3);
    for (const name of channelNames) expect(lockNames).not.toContain(name);
    for (const token of tokens) expect(JSON.stringify([messages, channelNames, lockNames])).not.toContain(token);
  } finally {
    ctrl.abort();
    await Promise.all(done);
  }
});

it("preserves dedicated streams on older browsers and refreshes a rotating credential on reconnect", async () => {
  const hub = gateway();
  const ctrl = new AbortController();
  let token = "first-session";
  const om = new OneMind({ baseUrl, token: { token: () => token }, fetch: hub.fetch, sleep: async () => {} });
  const done = om.events.subscribe({ signal: ctrl.signal }, () => {});
  try {
    await vi.waitFor(() => expect(hub.streams).toHaveLength(1));
    token = "second-session";
    hub.streams[0]!.controller.error(new Error("connection dropped"));
    await vi.waitFor(() => expect(hub.streams).toHaveLength(2));
    expect(hub.streams.map(s => s.headers.get("Authorization"))).toEqual(["Bearer first-session", "Bearer second-session"]);
    await expect(om.events.subscribeShared({}, () => {})).rejects.toMatchObject({ code: "stream_unavailable" });
  } finally {
    ctrl.abort();
    await done;
  }
  vi.stubGlobal("navigator", {});
  const olderBrowser = new OneMind({ baseUrl, token, fetch: hub.fetch });
  const stop = new AbortController();
  const direct = olderBrowser.events.subscribe({ signal: stop.signal }, () => {});
  try {
    await vi.waitFor(() => expect(hub.streams).toHaveLength(3));
    expect(request).not.toHaveBeenCalled();
  } finally {
    stop.abort();
    await direct;
  }
});

it("bounds a stalled subscriber's backlog while another tab continues receiving events in order", async () => {
  const hub = gateway();
  const om = new OneMind({ baseUrl, token: "shared-session", fetch: hub.fetch });
  const stop = new AbortController();
  const received: string[] = [];
  const fast = om.events.subscribeShared({ signal: stop.signal }, (event) => { received.push(event.id); });
  try {
    await vi.waitFor(() => expect(hub.connected).toBe(1));
    let release!: () => void;
    const waiting = new Promise<void>(resolve => { release = resolve; });
    const slow = om.events.subscribeShared({ signal: stop.signal }, () => waiting);
    const rejected = expect(slow).rejects.toMatchObject({ code: "slow_subscriber" });
    try {
      await vi.waitFor(() => expect(request).toHaveBeenCalledTimes(2));
      for (let i = 1; i <= 150; i++) send(hub.streams[0]!.controller, { type: "node.status", id: String(i) });
      await rejected;
      expect(received).toEqual(Array.from({ length: 150 }, (_, i) => String(i + 1)));
    } finally {
      release();
    }
  } finally {
    stop.abort();
    await fast;
  }
});

it("sends the protocol version on the shared feed's leader connection", async () => {
  const hub = gateway();
  const ctrl = new AbortController();
  const om = new OneMind({ baseUrl, token: "session-with-protocol", fetch: hub.fetch });
  const done = om.events.subscribeShared({ signal: ctrl.signal }, vi.fn());
  try {
    await vi.waitFor(() => expect(hub.connected).toBe(1));
    expect(hub.streams[0]!.headers.get("X-OneMind-Protocol")).toBe(String(PROTOCOL_VERSION));
    expect(hub.streams[0]!.headers.get("Authorization")).toBe("Bearer session-with-protocol");
  } finally {
    ctrl.abort();
    await done;
  }
});
