// SPDX-License-Identifier: Apache-2.0
import type { HubEvent } from '../api/types';
import { EventStream, SseParser, staleBy, toHubEvent, type StreamState, type XhrLike } from './events';

describe('SseParser', () => {
  it('parses events split across chunks, including a CRLF split in half', () => {
    const p = new SseParser();
    expect(p.feed('id: 18342\r')).toEqual([]);
    expect(p.feed('\nevent: action.state_changed\r\ndata: {"a":')).toEqual([]);
    const out = p.feed('1}\r\n\r\n');
    expect(out).toEqual([{ id: '18342', event: 'action.state_changed', data: '{"a":1}' }]);
    expect(p.lastEventId).toBe('18342');
  });

  it('ignores keepalive comments, joins multi-line data and reads retry', () => {
    const p = new SseParser();
    const out = p.feed(': keepalive\n\nretry: 5000\ndata: one\ndata: two\n\n');
    expect(out).toEqual([{ id: undefined, event: 'message', data: 'one\ntwo' }]);
    expect(p.retryMs).toBe(5000);
  });

  it('turns the §12.8 envelope into an event, and an empty stream.reset too', () => {
    const e = toHubEvent({ id: '7', event: 'node.status', data: '{"schema":"onemind.event/v1","id":"7","type":"node.status","ts":"t"}' });
    expect(e?.type).toBe('node.status');
    expect(toHubEvent({ id: '8', event: 'stream.reset', data: '' })?.type).toBe('stream.reset');
    expect(toHubEvent({ id: '9', event: 'x', data: 'not json' })).toBeUndefined();
  });

  it('maps event types to the data they make stale', () => {
    const ev = (type: string) => ({ schema: 'onemind.event/v1', id: '1', ts: '', type }) as HubEvent;
    expect(staleBy(ev('action.requested'))).toEqual(['actions']);
    expect(staleBy(ev('notification.created'))).toEqual(['inbox']);
    expect(staleBy(ev('stream.reset'))).toEqual(['all']);
    expect(staleBy(ev('automation.fired'))).toEqual([]);
  });
});

class FakeXhr implements XhrLike {
  static all: FakeXhr[] = [];
  readyState = 0;
  status = 0;
  responseText = '';
  onreadystatechange: (() => void) | null = null;
  onerror: (() => void) | null = null;
  headers: Record<string, string> = {};
  url = '';
  aborted = false;
  retryAfter: string | null = null;
  constructor() {
    FakeXhr.all.push(this);
  }
  open(_m: string, url: string) {
    this.url = url;
    this.readyState = 1;
  }
  setRequestHeader(k: string, v: string) {
    this.headers[k] = v;
  }
  send() {}
  abort() {
    this.aborted = true;
  }
  getResponseHeader(k: string) {
    return k === 'Retry-After' ? this.retryAfter : null;
  }
  answer(status: number) {
    this.status = status;
    this.readyState = 2;
    this.onreadystatechange?.();
  }
  push(text: string) {
    this.responseText += text;
    this.readyState = 3;
    this.onreadystatechange?.();
  }
  end() {
    this.readyState = 4;
    this.onreadystatechange?.();
  }
}

function open(over: Partial<ConstructorParameters<typeof EventStream>[0]> = {}) {
  const events: HubEvent[] = [];
  const states: StreamState[] = [];
  let token = 'tok';
  const s = new EventStream({
    url: 'https://h/v1/events',
    bearer: () => token,
    types: ['action.*', 'node.status'],
    onEvent: (e) => events.push(e),
    onState: (st) => states.push(st),
    makeXhr: () => new FakeXhr(),
    random: () => 0.5,
    ...over,
  });
  s.start();
  return { s, events, states, setToken: (t: string) => (token = t), last: () => FakeXhr.all[FakeXhr.all.length - 1]! };
}

const msg = (id: string, type: string) => `id: ${id}\nevent: ${type}\ndata: {"schema":"onemind.event/v1","id":"${id}","type":"${type}","ts":"t"}\n\n`;

describe('EventStream', () => {
  beforeEach(() => {
    FakeXhr.all = [];
    jest.useFakeTimers();
  });
  afterEach(() => jest.useRealTimers());

  it('sends the bearer and filter, delivers events, and resumes with Last-Event-ID after the server closes', () => {
    const { s, events, states, last } = open();
    const x = last();
    expect(x.url).toBe('https://h/v1/events?types=action.*%2Cnode.status');
    expect(x.headers.Authorization).toBe('Bearer tok');
    expect(x.headers.Accept).toBe('text/event-stream');
    x.answer(200);
    x.push(msg('41', 'action.requested') + ': keepalive\n\n');
    x.push(msg('42', 'node.status'));
    expect(events.map((e) => e.id)).toEqual(['41', '42']);
    expect(states).toEqual(['connecting', 'open']);
    x.end();
    expect(states[states.length - 1]).toBe('retrying');
    jest.advanceTimersByTime(1000);
    expect(FakeXhr.all).toHaveLength(2);
    expect(last().headers['Last-Event-ID']).toBe('42');
    s.stop();
    expect(last().aborted).toBe(true);
  });

  it('backs off exponentially on network errors and resets after a good connection', () => {
    const { s, last } = open();
    last().onerror!();
    jest.advanceTimersByTime(999);
    expect(FakeXhr.all).toHaveLength(1);
    jest.advanceTimersByTime(1);
    expect(FakeXhr.all).toHaveLength(2);
    last().onerror!();
    jest.advanceTimersByTime(1999);
    expect(FakeXhr.all).toHaveLength(2);
    jest.advanceTimersByTime(1);
    expect(FakeXhr.all).toHaveLength(3);
    s.stop();
  });

  it('stops for good when the gateway has no stream (404)', () => {
    const { states, last } = open();
    last().answer(404);
    expect(states[states.length - 1]).toBe('unsupported');
    jest.advanceTimersByTime(60_000);
    expect(FakeXhr.all).toHaveLength(1);
  });

  it('a 403 (no events:read, e.g. a child or guest) stops the stream without signing out or renewing', async () => {
    let refreshed = 0;
    const { states, last } = open({ refresh: async () => (refreshed++, 'fresh') });
    last().answer(403);
    await Promise.resolve();
    expect(states[states.length - 1]).toBe('forbidden');
    expect(states).not.toContain('unauthenticated');
    expect(refreshed).toBe(0);
    jest.advanceTimersByTime(60_000);
    expect(FakeXhr.all).toHaveLength(1);
  });

  it('renews an expired session once, then reconnects with the new token', async () => {
    let refreshed = 0;
    const h = open({
      refresh: async () => {
        refreshed++;
        h.setToken('fresh');
        return 'fresh';
      },
    });
    h.last().answer(401);
    await Promise.resolve();
    await Promise.resolve();
    expect(refreshed).toBe(1);
    expect(h.last().headers.Authorization).toBe('Bearer fresh');
    h.last().answer(401);
    expect(h.states[h.states.length - 1]).toBe('unauthenticated');
  });

  it('honours Retry-After on 503', () => {
    const { s, last } = open();
    last().retryAfter = '10';
    last().answer(503);
    jest.advanceTimersByTime(9999);
    expect(FakeXhr.all).toHaveLength(1);
    jest.advanceTimersByTime(1);
    expect(FakeXhr.all).toHaveLength(2);
    s.stop();
  });

  it('treats a silent connection as dead and reconnects', () => {
    const { s, last } = open({ idleMs: 45_000 });
    last().answer(200);
    jest.advanceTimersByTime(45_000);
    expect(last().aborted).toBe(true);
    jest.advanceTimersByTime(1000);
    expect(FakeXhr.all).toHaveLength(2);
    s.stop();
  });

  it('rotates the connection after rotateBytes so the text buffer stays small', () => {
    const { s, last } = open({ rotateBytes: 100 });
    last().answer(200);
    last().push(msg('1', 'node.status') + msg('2', 'node.status'));
    expect(FakeXhr.all).toHaveLength(2);
    expect(last().headers['Last-Event-ID']).toBe('2');
    s.stop();
  });
});
