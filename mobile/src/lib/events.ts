// SPDX-License-Identifier: Apache-2.0
// The live events stream (contract §12.8): `GET /v1/events` as server-sent events.
// React Native's fetch cannot read a body while it is still arriving, but its XMLHttpRequest
// delivers text incrementally, so the stream runs over XHR. No library: the parser follows the
// HTML "server-sent events" rules and is small enough to test line by line.
//
// The stream only tells the app *that* something changed. Screens still read state over REST,
// so a missed event costs a refresh, never a wrong screen.
import type { HubEvent } from '../api/types';

export interface SseMessage {
  id: string | undefined;
  event: string;
  data: string;
}

/** Incremental SSE parser: feed chunks as they arrive, get complete messages back. */
export class SseParser {
  private buf = '';
  private data: string[] = [];
  private event = '';
  /** The last `id:` seen (sent back as Last-Event-ID on reconnect). */
  lastEventId: string | undefined;
  /** The last `retry:` seen, in ms. */
  retryMs: number | undefined;

  feed(chunk: string): SseMessage[] {
    this.buf += chunk;
    const out: SseMessage[] = [];
    for (;;) {
      const m = /\r\n|\r|\n/.exec(this.buf);
      if (!m) break;
      // A lone \r at the very end may be the first half of \r\n: wait for the next chunk.
      if (m[0] === '\r' && m.index === this.buf.length - 1) break;
      const line = this.buf.slice(0, m.index);
      this.buf = this.buf.slice(m.index + m[0].length);
      this.line(line, out);
    }
    return out;
  }

  private line(line: string, out: SseMessage[]) {
    if (line === '') {
      if (this.data.length) out.push({ id: this.lastEventId, event: this.event || 'message', data: this.data.join('\n') });
      this.data = [];
      this.event = '';
      return;
    }
    if (line.startsWith(':')) return; // comment, e.g. ": keepalive"
    const c = line.indexOf(':');
    const field = c < 0 ? line : line.slice(0, c);
    const value = c < 0 ? '' : line.slice(c + 1).replace(/^ /, '');
    if (field === 'data') this.data.push(value);
    else if (field === 'event') this.event = value;
    else if (field === 'id' && !value.includes('\0')) this.lastEventId = value;
    else if (field === 'retry' && /^\d+$/.test(value)) this.retryMs = Number(value);
  }
}

/** Parse one message into the §12.8 envelope; anything else is ignored (clients ignore unknown types). */
export function toHubEvent(m: SseMessage): HubEvent | undefined {
  try {
    const v = JSON.parse(m.data) as Partial<HubEvent>;
    if (typeof v !== 'object' || v === null || typeof v.type !== 'string') return undefined;
    return { schema: 'onemind.event/v1', id: String(v.id ?? m.id ?? ''), ts: String(v.ts ?? ''), ...v } as HubEvent;
  } catch {
    // `stream.reset` may arrive with an empty body; the event name is enough.
    return m.event === 'stream.reset' ? { schema: 'onemind.event/v1', id: m.id ?? '', type: 'stream.reset', ts: '' } : undefined;
  }
}

/** The parts of XMLHttpRequest the stream uses (so tests can drive it). */
export interface XhrLike {
  readyState: number;
  status: number;
  responseText: string;
  onreadystatechange: (() => void) | null;
  onerror: (() => void) | null;
  open(method: string, url: string): void;
  setRequestHeader(name: string, value: string): void;
  send(): void;
  abort(): void;
  getResponseHeader(name: string): string | null;
}

export type StreamState = 'connecting' | 'open' | 'retrying' | 'stopped' | 'unsupported' | 'unauthenticated';

export interface EventStreamOptions {
  url: string;
  bearer: () => string | undefined;
  /** Renew an expired session once (same as REST); undefined → the stream reports `unauthenticated`. */
  refresh?: () => Promise<string | undefined>;
  /** §12.8 `types` filter, e.g. ['action.*', 'node.status']. Empty: everything this person may read. */
  types?: string[];
  onEvent: (e: HubEvent) => void;
  onState?: (s: StreamState) => void;
  lastEventId?: string;
  makeXhr?: () => XhrLike;
  /** Reconnect (with Last-Event-ID) after this many bytes, so the XHR's text buffer stays small. */
  rotateBytes?: number;
  /** No byte for this long (the gateway sends a keepalive every 15 s) → the connection is dead. */
  idleMs?: number;
  random?: () => number;
}

const BACKOFF_MIN_MS = 1000;
const BACKOFF_MAX_MS = 30_000;

/** One reconnecting SSE connection. Call start() once and stop() when the screen or app goes away. */
export class EventStream {
  private xhr: XhrLike | undefined;
  private parser = new SseParser();
  private seen = 0;
  private bytes = 0;
  private attempt = 0;
  private retryTimer: ReturnType<typeof setTimeout> | undefined;
  private idleTimer: ReturnType<typeof setTimeout> | undefined;
  private stopped = true;
  private renewed = false;
  private state: StreamState = 'stopped';
  private lastId: string | undefined;
  private readonly o: Required<Pick<EventStreamOptions, 'rotateBytes' | 'idleMs' | 'random'>> & EventStreamOptions;

  constructor(opts: EventStreamOptions) {
    this.o = { rotateBytes: 1_000_000, idleMs: 45_000, random: Math.random, ...opts };
    this.lastId = opts.lastEventId;
  }

  get lastEventId() {
    return this.lastId;
  }

  start() {
    if (!this.stopped) return;
    this.stopped = false;
    this.connect();
  }

  stop() {
    this.stopped = true;
    this.teardown();
    this.setState('stopped');
  }

  private setState(s: StreamState) {
    if (s === this.state) return;
    this.state = s;
    this.o.onState?.(s);
  }

  private teardown() {
    if (this.retryTimer !== undefined) clearTimeout(this.retryTimer);
    if (this.idleTimer !== undefined) clearTimeout(this.idleTimer);
    this.retryTimer = this.idleTimer = undefined;
    const x = this.xhr;
    this.xhr = undefined;
    if (x) {
      x.onreadystatechange = null;
      x.onerror = null;
      x.abort();
    }
  }

  private armIdle() {
    if (this.idleTimer !== undefined) clearTimeout(this.idleTimer);
    this.idleTimer = setTimeout(() => this.retry(), this.o.idleMs);
  }

  private connect() {
    this.teardown();
    if (this.stopped) return;
    this.setState(this.attempt === 0 ? 'connecting' : 'retrying');
    const x = (this.o.makeXhr ?? (() => new XMLHttpRequest() as unknown as XhrLike))();
    this.xhr = x;
    this.parser = new SseParser();
    this.seen = 0;
    this.bytes = 0;
    const qs = this.o.types?.length ? `?types=${encodeURIComponent(this.o.types.join(','))}` : '';
    x.open('GET', this.o.url + qs);
    x.setRequestHeader('Accept', 'text/event-stream');
    x.setRequestHeader('Cache-Control', 'no-cache');
    x.setRequestHeader('OneMind-API-Version', '1');
    const bearer = this.o.bearer();
    if (bearer) x.setRequestHeader('Authorization', `Bearer ${bearer}`);
    if (this.lastId) x.setRequestHeader('Last-Event-ID', this.lastId);
    x.onreadystatechange = () => this.onChange(x);
    x.onerror = () => {
      if (x === this.xhr) this.retry();
    };
    x.send();
    this.armIdle();
  }

  private onChange(x: XhrLike) {
    if (x !== this.xhr || x.readyState < 2) return;
    if (x.status !== 200) {
      if (x.readyState === 4 || x.readyState === 2) this.refused(x);
      return;
    }
    if (this.state !== 'open') {
      this.attempt = 0;
      this.renewed = false;
      this.setState('open');
    }
    this.armIdle();
    const text = x.responseText ?? '';
    if (text.length > this.seen) {
      const chunk = text.slice(this.seen);
      this.seen = text.length;
      this.bytes += chunk.length;
      for (const m of this.parser.feed(chunk)) {
        if (m.id !== undefined) this.lastId = m.id;
        const e = toHubEvent(m);
        if (e) this.o.onEvent(e);
      }
      if (this.parser.lastEventId !== undefined) this.lastId = this.parser.lastEventId;
    }
    if (x.readyState === 4) this.retry(); // the server closed the stream: resume from lastId
    else if (this.bytes >= this.o.rotateBytes) this.connect();
  }

  private refused(x: XhrLike) {
    const status = x.status;
    if (status === 0) return this.retry(); // network failure surfaces as status 0
    this.teardown();
    if (status === 404) {
      this.stopped = true;
      return this.setState('unsupported');
    }
    if (status === 401 || status === 403) {
      if (status === 401 && this.o.refresh && !this.renewed) {
        this.renewed = true;
        void this.o.refresh().then((t) => {
          if (this.stopped) return;
          if (t) this.connect();
          else {
            this.stopped = true;
            this.setState('unauthenticated');
          }
        });
        return;
      }
      this.stopped = true;
      return this.setState('unauthenticated');
    }
    const after = Number(x.getResponseHeader('Retry-After'));
    this.retry(Number.isFinite(after) && after > 0 ? after * 1000 : undefined);
  }

  /** Exponential backoff with ±20 % jitter, honouring the server's `retry:` or Retry-After. */
  private retry(minMs?: number) {
    this.teardown();
    if (this.stopped) return;
    this.setState('retrying');
    const base = Math.min(BACKOFF_MAX_MS, BACKOFF_MIN_MS * 2 ** this.attempt);
    this.attempt += 1;
    const jitter = 0.8 + this.o.random() * 0.4;
    const wait = Math.max(minMs ?? 0, this.parser.retryMs ?? 0, Math.round(base * jitter));
    this.retryTimer = setTimeout(() => this.connect(), wait);
  }
}

/** Which data an event means is out of date. */
export function staleBy(e: HubEvent): Array<'actions' | 'nodes' | 'apps' | 'inbox' | 'alerts' | 'all'> {
  const t = e.type;
  if (t === 'stream.reset') return ['all'];
  if (t.startsWith('action.')) return ['actions'];
  if (t.startsWith('node.')) return ['nodes'];
  if (t.startsWith('app.')) return ['apps'];
  if (t.startsWith('notification.')) return ['inbox'];
  if (t.startsWith('alert.')) return ['alerts'];
  return [];
}
