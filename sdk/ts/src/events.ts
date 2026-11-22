// SPDX-License-Identifier: Apache-2.0
// GET /v1/events (contract §12.8) over fetch streaming, so the token stays in a header (the
// browser EventSource cannot set one). Reconnects with backoff and resumes with Last-Event-ID.
// React Native has no streaming fetch body: pass your own `transport` there.

import type { OneMind } from "./client.js";
import { errorFor, OneMindError } from "./errors.js";
import { canShareEvents, sharedEvents, type SharedEventOptions } from "./shared-events.js";
export type { SharedEventOptions } from "./shared-events.js";

export interface OneMindEvent {
  schema?: string;
  id: string;
  type: string;
  ts?: string;
  subject?: Record<string, unknown>;
  data?: Record<string, unknown>;
  actor_id?: string;
}

export interface SubscribeOptions {
  types?: string[];
  sinceId?: string;
  signal?: AbortSignal;
  /** Reconnect when no byte arrives for this long (default 45 000 ms). */
  silenceMs?: number;
  /** Replace the fetch-based reader (React Native, tests). Yields raw text chunks. */
  transport?: (url: string, headers: Record<string, string>, signal: AbortSignal) => AsyncIterable<string>;
}

export class EventsApi {
  constructor(private readonly om: OneMind, private readonly fixedBearer = false) {}

  /**
   * Calls onEvent for each event until the signal aborts or onEvent throws. A 401/403/404 rejects
   * (404: this hub has no event stream yet; poll instead). `stream.reset` means reload over REST.
   */
  async subscribe(opts: SubscribeOptions, onEvent: (e: OneMindEvent) => void | Promise<void>): Promise<void> {
    // The dashboard's ordinary live subscription can share one feed. An explicit replay,
    // server-side type selector or caller-supplied transport retains its original semantics.
    if (this.fixedBearer && canShareEvents() && !opts.types?.length && opts.sinceId === undefined &&
        !opts.transport && opts.silenceMs === undefined) {
      return this.subscribeShared(opts, onEvent);
    }
    return this.read(opts, onEvent);
  }

  /** Subscribe to the browser's single live feed for this hub and bearer session. */
  async subscribeShared(opts: SharedEventOptions, onEvent: (e: OneMindEvent) => void | Promise<void>): Promise<void> {
    if (opts.signal?.aborted) return;
    if (!this.fixedBearer) {
      throw new OneMindError(0, "stream_unavailable", "Shared events require the current session's fixed bearer token");
    }
    const headers = await this.om.authHeader();
    return sharedEvents(this.om.baseUrl, headers.Authorization!, opts,
      (signal, sinceId, emit) => this.read({ signal, sinceId }, emit, headers), onEvent);
  }

  private async read(opts: SubscribeOptions, onEvent: (e: OneMindEvent, id: string) => void | Promise<void>,
                     auth?: Record<string, string>): Promise<void> {
    let last = opts.sinceId ?? "";
    let delay = 1000;
    for (;;) {
      if (opts.signal?.aborted) return;
      try {
        const retry = await this.once(opts, last, async (e, id) => {
          if (id) last = id;
          await onEvent(e, id);
        }, auth);
        if (retry) delay = retry;
      } catch (e) {
        if (opts.signal?.aborted) return;
        if (e instanceof OneMindError && e.status >= 400 && e.status < 500 && e.status !== 429) throw e;
        if (!(e instanceof OneMindError)) throw e; // thrown by onEvent: stop
      }
      if (opts.signal?.aborted) return;
      let wake: (() => void) | undefined;
      const aborted = new Promise<void>(resolve => { wake = resolve; });
      opts.signal?.addEventListener("abort", wake!, { once: true });
      try {
        await Promise.race([this.om.sleep(delay / 2 + Math.random() * (delay / 2)), aborted]);
      } finally {
        opts.signal?.removeEventListener("abort", wake!);
      }
      delay = Math.min(30_000, delay * 2);
    }
  }

  private async once(opts: SubscribeOptions, last: string, emit: (e: OneMindEvent, id: string) => Promise<void>,
                     auth?: Record<string, string>) {
    this.om.checkTransport();
    const qs = opts.types?.length ? `?types=${encodeURIComponent(opts.types.join(","))}` : "";
    const url = `${this.om.baseUrl}/v1/events${qs}`;
    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      ...(auth ?? await this.om.authHeader()),
      ...(last ? { "Last-Event-ID": last } : {}),
    };
    const ctrl = new AbortController();
    const onAbort = () => ctrl.abort();
    if (opts.signal?.aborted) return 0;
    opts.signal?.addEventListener("abort", onAbort);
    let silence: ReturnType<typeof setTimeout> | undefined;
    const alive = () => {
      clearTimeout(silence);
      silence = setTimeout(() => ctrl.abort(), opts.silenceMs ?? 45_000);
    };
    let retry = 0;
    try {
      alive();
      const chunks = opts.transport ? opts.transport(url, headers, ctrl.signal) : this.fetchChunks(url, headers, ctrl.signal);
      let buf = "";
      for await (const chunk of chunks) {
        alive();
        buf += chunk;
        let i: number;
        while ((i = buf.search(/\r?\n\r?\n/)) >= 0) {
          const block = buf.slice(0, i);
          buf = buf.slice(i + (buf[i] === "\r" ? 4 : 2));
          let id = "";
          let type = "";
          const data: string[] = [];
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith(":")) continue;
            const j = line.indexOf(":");
            const k = j < 0 ? line : line.slice(0, j);
            const v = j < 0 ? "" : line.slice(j + 1).replace(/^ /, "");
            if (k === "id") id = v;
            else if (k === "event") type = v;
            else if (k === "data") data.push(v);
            else if (k === "retry" && /^\d+$/.test(v)) retry = Number(v);
          }
          if (!data.length) continue;
          let ev: OneMindEvent;
          try {
            ev = JSON.parse(data.join("\n")) as OneMindEvent;
          } catch {
            ev = { id, type, data: { raw: data.join("\n") } };
          }
          ev.type ||= type;
          await emit(ev, id);
        }
      }
    } finally {
      ctrl.abort();
      clearTimeout(silence);
      opts.signal?.removeEventListener("abort", onAbort);
    }
    return retry;
  }

  private async *fetchChunks(url: string, headers: Record<string, string>, signal: AbortSignal): AsyncIterable<string> {
    let res: Response;
    try {
      res = await this.om.fetchImpl(url, { headers, signal });
    } catch {
      throw new OneMindError(0, "network", "could not reach the hub");
    }
    if (!res.ok) {
      const b = (await res.json().catch(() => undefined)) as { error?: string; message?: string } | undefined;
      throw errorFor(res.status, b?.error ?? (res.status === 404 ? "not_found" : "unexpected_response"), b?.message ?? `HTTP ${res.status}`);
    }
    if (!res.body) throw new OneMindError(0, "network", "this runtime has no streaming fetch body; pass `transport`");
    const reader = res.body.getReader();
    const dec = new TextDecoder();
    try {
      for (;;) {
        const { done, value } = await reader.read();
        if (done) return;
        yield dec.decode(value, { stream: true });
      }
    } catch {
      throw new OneMindError(0, "network", "event stream closed");
    }
  }
}
