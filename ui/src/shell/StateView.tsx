// SPDX-License-Identifier: Apache-2.0
// The empty-state system: one component renders loading, empty, error, stale, offline and
// forbidden the same way everywhere, and renders its children when the data is usable.
import { useId, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { formatAgo } from '../lib/time';
import { ERROR_COPY, EMPTY_PRESETS, type EmptyPreset, type EmptyPresetId, type GatewayError, type ViewState } from './states';
import { ShellIcon, type ShellIconName } from './icons';
import './shell.css';

/** Layout-shaped placeholder. Hidden from assistive tech; the caller's status text is read instead. */
export function Skeleton({ rows = 3, variant = 'list' }: { rows?: number; variant?: 'list' | 'cards' | 'text' }) {
  return (
    <div className={cx('oms-skel', `oms-skel-${variant}`)} aria-hidden="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="oms-skel-row">
          {variant !== 'text' && <span className="oms-skel-block oms-skel-avatar" />}
          <span className="oms-skel-lines">
            <span className="oms-skel-block oms-skel-line" style={{ width: `${70 - ((i * 13) % 30)}%` }} />
            {variant !== 'text' && <span className="oms-skel-block oms-skel-line oms-skel-line-sub" style={{ width: `${45 - ((i * 7) % 15)}%` }} />}
          </span>
        </div>
      ))}
    </div>
  );
}

/** Our own generated illustration: concentric rings with the subject icon in the middle. */
function Emblem({ icon, tone }: { icon: ShellIconName; tone: 'calm' | 'warn' | 'bad' }) {
  return (
    <span className={cx('oms-emblem', `oms-emblem-${tone}`)} aria-hidden="true">
      <svg className="oms-emblem-rings" viewBox="0 0 120 120" width="120" height="120">
        <circle cx="60" cy="60" r="58" />
        <circle cx="60" cy="60" r="44" />
        <circle cx="60" cy="60" r="30" />
      </svg>
      <span className="oms-emblem-core">
        <ShellIcon name={icon} size={26} />
      </span>
    </span>
  );
}

export interface StateViewProps {
  state: ViewState;
  /** A preset from EMPTY_PRESETS, or your own copy. */
  empty?: EmptyPresetId | EmptyPreset;
  error?: GatewayError;
  /** Seconds since the data was confirmed, for stale/offline. */
  ageSeconds?: number;
  /** What is loading, for the status text: "Loading notifications". */
  what?: string;
  /** Loading has passed 10 s: say what is slow. */
  slow?: boolean;
  onRetry?: () => void;
  /** Extra action for the empty state, e.g. "Open the Market". */
  action?: ReactNode;
  /** Who can see this, for forbidden: "Only the owner can see backups." */
  forbiddenReason?: string;
  compact?: boolean;
  skeleton?: 'list' | 'cards' | 'text';
  /** Rendered for ready, stale and offline (under the banner). */
  children?: ReactNode;
}

export function StateView({
  state,
  empty = 'search',
  error,
  ageSeconds,
  what = 'Loading',
  slow,
  onRetry,
  action,
  forbiddenReason,
  compact,
  skeleton = 'list',
  children,
}: StateViewProps) {
  const titleId = useId();
  if (state === 'loading') {
    return (
      <div className="oms-state oms-state-loading">
        <p role="status" className={slow ? 'oms-slow' : 'om-visually-hidden'}>
          {slow ? `${what} is taking longer than usual. The hub may be busy; this page keeps trying.` : `${what}…`}
        </p>
        <Skeleton variant={skeleton} rows={compact ? 2 : 4} />
      </div>
    );
  }

  if (state === 'stale' || state === 'offline') {
    const offline = state === 'offline';
    return (
      <div className="oms-state oms-state-data">
        <div className={cx('oms-banner', offline ? 'om-tone-neutral' : 'om-tone-warn')} role="status">
          <ShellIcon name={offline ? 'offline' : 'clock'} size={18} />
          <span>
            <strong>{offline ? 'Offline. ' : 'Not live. '}</strong>
            {`Showing the last report from ${formatAgo(ageSeconds ?? Number.NaN)}.`}
            {offline ? ' Changes are paused until the hub answers.' : ''}
          </span>
          {onRetry && (
            <button type="button" className="om-btn om-btn-ghost om-btn-sm oms-banner-btn" onClick={onRetry}>
              Retry now
            </button>
          )}
        </div>
        <div className={cx('oms-dimmed', offline && 'oms-dimmed-more')}>{children}</div>
      </div>
    );
  }

  if (state === 'ready') return <>{children}</>;

  let icon: ShellIconName;
  let tone: 'calm' | 'warn' | 'bad' = 'calm';
  let title: string;
  let body: ReactNode;
  let command: string | undefined;
  let foot: ReactNode = null;

  if (state === 'error') {
    icon = 'alert';
    tone = 'bad';
    title = error ? ERROR_COPY[error.error] : 'Something went wrong';
    body = error && (
      <>
        <span className="oms-err-msg">{error.message}</span>
        <code className="oms-err-code">{error.error}</code>
      </>
    );
    foot = onRetry && (
      <button type="button" className="om-btn om-btn-secondary om-btn-sm" onClick={onRetry}>
        <ShellIcon name="updates" size={16} />
        Try again
      </button>
    );
  } else if (state === 'forbidden') {
    icon = 'lock';
    tone = 'warn';
    title = 'Not available to you';
    body = forbiddenReason ?? ERROR_COPY.permission_denied;
  } else {
    const p: EmptyPreset = typeof empty === 'string' ? EMPTY_PRESETS[empty] : empty;
    icon = p.icon;
    title = p.title;
    body = p.body;
    command = p.command;
    foot = action;
  }

  return (
    <div className={cx('oms-state', `oms-state-${state}`, compact && 'oms-state-compact')} role={state === 'error' ? 'alert' : 'note'} aria-labelledby={titleId}>
      {!compact && <Emblem icon={icon} tone={tone} />}
      {compact && (
        <span className={cx('oms-state-mini', `oms-emblem-${tone}`)} aria-hidden="true">
          <ShellIcon name={icon} size={20} />
        </span>
      )}
      <p id={titleId} className="oms-state-title">
        {title}
      </p>
      {body && <p className="oms-state-body">{body}</p>}
      {command && (
        <p className="oms-state-cmd">
          <span className="om-visually-hidden">Or from a terminal: </span>
          <code>{command}</code>
        </p>
      )}
      {foot && <div className="oms-state-foot">{foot}</div>}
    </div>
  );
}
