// SPDX-License-Identifier: Apache-2.0
import type { OneMindEvent } from "./events.js";
import { OneMindError, errorFor } from "./errors.js";

export interface SharedEventOptions {
  signal?: AbortSignal;
  /** Asset kind, or the event domain (e.g. "node" for node.status). */
  kind?: string;
  /** The area_id of the event's subject or payload. */
  area?: string;
  /** West, south, east, north in degrees. West > east crosses the antimeridian. */
  bbox?: readonly [number, number, number, number];
}

function matches(event: OneMindEvent, opts: SharedEventOptions): boolean {
  if (event.type === "stream.reset") return true;
  const { data, subject } = event;
  const kind = data?.kind ?? subject?.kind ?? event.type.split(".")[0];
  if (opts.kind && opts.kind !== kind) return false;
  if (opts.area && opts.area !== (subject?.area_id ?? data?.area_id)) return false;
  if (!opts.bbox) return true;
  const position = data?.position ?? data;
  if (!position || typeof position !== "object" || !("lat" in position) || !("lon" in position)) return false;
  const { lat, lon } = position;
  if (typeof lat !== "number" || typeof lon !== "number" || !Number.isFinite(lat) || !Number.isFinite(lon)) return false;
  const [west, south, east, north] = opts.bbox;
  return lat >= south && lat <= north && (west > east ? lon >= west || lon <= east : lon >= west && lon <= east);
}

type RecordMessage = { event: OneMindEvent; cursor: string };
type FailureMessage = { status: number; code: string };
type OpenStream = (signal: AbortSignal, cursor: string, emit: (event: OneMindEvent, id: string) => void) => Promise<void>;

export function canShareEvents(): boolean {
  return typeof window !== "undefined" && !!globalThis.navigator?.locks && !!globalThis.crypto?.subtle &&
    typeof BroadcastChannel !== "undefined";
}

async function digest(value: string): Promise<string> {
  const bytes = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), byte => byte.toString(16).padStart(2, "0")).join("");
}

/**
 * Each subscriber queues for one origin-wide Web Lock. Only its holder opens the gateway
 * connection. When a tab disappears the browser releases its locks and the next tab resumes.
 */
export async function sharedEvents(
  hub: string, authorization: string, opts: SharedEventOptions, open: OpenStream,
  onEvent: (event: OneMindEvent) => void | Promise<void>,
): Promise<void> {
  if (opts.signal?.aborted) return;
  if (!canShareEvents()) {
    throw new OneMindError(0, "stream_unavailable", "Shared events require a secure browser context with Web Locks and BroadcastChannel");
  }
  // Lock names are enumerable by other tabs. Never expose the channel capability in a lock
  // name, or put a bearer token in either name, local storage, or a broadcast message.
  const channelName = await digest(JSON.stringify(["onemind.events.v1", hub, authorization]));
  const lockName = await digest(channelName);
  if (opts.signal?.aborted) return;
  const channel = new BroadcastChannel(channelName);
  const lifetime = new AbortController();
  const stop = () => lifetime.abort();
  opts.signal?.addEventListener("abort", stop, { once: true });
  let cursor = "";
  let failure: { error: unknown } | undefined;
  let delivered = Promise.resolve();
  let pending = 0;
  function fail(error: unknown) {
    failure = { error };
    stop();
  }
  function receive(record: RecordMessage) {
    if (lifetime.signal.aborted) return;
    if (record.cursor) cursor = record.cursor;
    if (matches(record.event, opts)) {
      // A slow handler only holds its own queue. Keep other windows live and bound memory.
      if (pending >= 128) {
        fail(new OneMindError(0, "slow_subscriber", "Reload the view and subscribe again"));
        return;
      }
      pending++;
      delivered = delivered.then(async () => {
        if (!lifetime.signal.aborted) await onEvent(record.event);
      }).catch(fail).finally(() => { pending--; });
    }
  }
  channel.onmessage = ({ data }: MessageEvent<RecordMessage | FailureMessage>) => {
    if ("event" in data) receive(data);
    else fail(errorFor(data.status, data.code, "Event stream unavailable"));
  };
  try {
    await navigator.locks.request(lockName, { signal: lifetime.signal }, async () => {
      try {
        await open(lifetime.signal, cursor, (event, id) => {
          if (lifetime.signal.aborted) return;
          const record = { event, cursor: id || (event.type === "stream.reset" ? event.id : "") };
          channel.postMessage(record);
          receive(record); // a BroadcastChannel does not deliver to its own sender
        });
      } catch (e) {
        if (lifetime.signal.aborted) return;
        const error = e instanceof OneMindError ? e : new OneMindError(0, "unexpected_response", "Event stream unavailable");
        channel.postMessage({ status: error.status, code: error.code } satisfies FailureMessage);
        fail(error);
      }
    });
  } catch (e) {
    if (!lifetime.signal.aborted) throw e;
  } finally {
    channel.close();
    opts.signal?.removeEventListener("abort", stop);
  }
  if (failure) throw failure.error;
}
