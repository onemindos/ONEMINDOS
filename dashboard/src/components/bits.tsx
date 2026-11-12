import type { ApiError, NodeStatus, PrincipalKind } from '../api/types';
import { formatAgo } from '../lib/time';

/**
 * App tile icon. v0 draws an original monogram tile (first letter on a colour
 * derived from the app id) instead of loading the manifest's `icon` file,
 * because contract v0 has no route that serves app icons yet.
 */
export function AppIcon({ id, name, size = 56 }: { id: string; name: string; size?: number }) {
  let h = 0;
  for (const ch of id) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span
      className="app-icon"
      aria-hidden="true"
      style={{ width: size, height: size, fontSize: size * 0.45, background: `hsl(${h} 55% 32%)` }}
    >
      {name.slice(0, 1).toUpperCase()}
    </span>
  );
}

const STATUS_TEXT: Record<NodeStatus, string> = { online: 'Online', stale: 'Stale', offline: 'Offline' };

/** Status is always written in words, never colour alone (WCAG 1.4.1). */
export function StatusBadge({ status }: { status: NodeStatus }) {
  return (
    <span className={`badge badge-${status}`}>
      <span className="dot" aria-hidden="true" />
      {STATUS_TEXT[status]}
    </span>
  );
}

export function KindBadge({ kind }: { kind: PrincipalKind | undefined }) {
  const label = kind === 'agent' ? 'AI agent' : kind === 'person' ? 'Person' : 'Unknown requester';
  return <span className={`badge badge-kind-${kind ?? 'unknown'}`}>{label}</span>;
}

export function ErrorNote({ error, fetchedAt, now }: { error: ApiError; fetchedAt?: number; now: number }) {
  return (
    <p className="note note-error" role="alert">
      Could not reach the hub ({error.code}: {error.message}).
      {fetchedAt !== undefined
        ? ` Showing data fetched ${formatAgo(Math.floor((now - fetchedAt) / 1000))}; it may be out of date.`
        : ''}
    </p>
  );
}

export function Loading({ what }: { what: string }) {
  return (
    <p className="note" role="status">
      Loading {what}…
    </p>
  );
}
