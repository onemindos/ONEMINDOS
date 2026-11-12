// SPDX-License-Identifier: Apache-2.0
// Building blocks shared by the Settings sections, Activity and Approvals.
import './settings.css';
import { Children, useId, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { formatAgo, secondsSince } from '../lib/time';
import type { Tone } from '../tokens/tokens';
import { Button } from '../components/Button';
import { Icon, type IconName } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { errorText } from './logic';
import type { Loadable } from './types';

/* ---------- icons ---------- */
// Drawn for OneMind in the Icon.tsx style (24 px grid, 1.75 stroke, round caps). flow and radio
// are the TAXONOMY §1.2 paths. No third-party icon was used or traced.
const SET_PATHS = {
  key: 'M8 15a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM11 11h10M18 11v3M15 11v2',
  users: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM2.5 20c0-3.6 2.9-5.5 6.5-5.5s6.5 1.9 6.5 5.5M16 4.5a3.5 3.5 0 0 1 0 6.5M18 14.8c2.2.6 3.5 2.4 3.5 5.2',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z',
  disk: 'M4 6h16v12H4zM4 14h16M16.5 16h.01M8 10h8',
  flow: 'M4 4h6v5H4zM14 15h6v5h-6zM7 9v4h10v2',
  radio: 'M12 12h.01M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8',
  shield: 'M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6z',
  copy: 'M9 9h11v11H9zM5 15H4V4h11v1',
  eye: 'M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  back: 'M15 6l-6 6 6 6',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  pause: 'M8 5v14M16 5v14',
  hash: 'M5 9h15M4 15h15M10 3L8 21M16 3l-2 18',
} as const;
export type SetIconName = keyof typeof SET_PATHS | IconName;

export function SetIcon({ name, size = 20, label }: { name: SetIconName; size?: number; label?: string }) {
  if (!(name in SET_PATHS)) return <Icon name={name as IconName} size={size} label={label} />;
  return (
    <svg
      className="om-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={SET_PATHS[name as keyof typeof SET_PATHS]} />
    </svg>
  );
}

/* ---------- async states ---------- */

export function Skeleton({ rows = 3, label }: { rows?: number; label: string }) {
  return (
    <div className="om-set-skeleton" role="status" aria-live="polite">
      <span className="om-visually-hidden">Loading {label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="om-set-skel-row" aria-hidden="true">
          <span className="om-set-skel om-set-skel-dot" />
          <span className="om-set-skel-lines">
            <span className="om-set-skel" style={{ width: `${62 - i * 9}%` }} />
            <span className="om-set-skel om-set-skel-thin" style={{ width: `${38 + i * 7}%` }} />
          </span>
        </div>
      ))}
    </div>
  );
}

export interface AsyncProps<T> {
  value: Loadable<T>;
  /** What is being shown, in words: "sessions", "backup destinations". */
  label: string;
  now: number;
  rows?: number;
  onRetry?: () => void;
  /** True when the ready data has nothing to show; renders `empty` instead of children. */
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T, live: boolean) => ReactNode;
}

/**
 * One panel's data in one of four honest states (IA §4): a skeleton while loading, the error
 * code and message with Retry, the last known copy with its age when stale, or the content.
 */
export function Async<T>({ value, label, now, rows, onRetry, isEmpty, empty, children }: AsyncProps<T>) {
  if (value.status === 'loading') return <Skeleton rows={rows} label={label} />;
  if (value.status === 'error')
    return (
      <div className="om-set-error om-tone-bad" role="alert">
        <SetIcon name="alert" />
        <div className="om-set-error-text">
          <p>
            <strong>Could not load {label}.</strong> {errorText(value.error)}
          </p>
          <p className="om-set-meta">
            <code>{value.error.error}</code> · {value.error.message}
          </p>
        </div>
        {onRetry && (
          <Button size="sm" onClick={onRetry}>
            Retry
          </Button>
        )}
      </div>
    );
  const live = !value.stale;
  return (
    <div className={cx('om-set-async', !live && 'om-set-stale')}>
      {!live && (
        <p className="om-set-stale-note" role="status">
          <StatusPill tone="warn" label="Last known" detail={formatAgo(secondsSince(value.asOf, now))} />
          <span>The hub is not answering. This is the last copy it sent, not live. Changes are paused.</span>
        </p>
      )}
      {isEmpty?.(value.data) ? empty : children(value.data, live)}
    </div>
  );
}

/** EmptyState markup (same classes) that also takes the settings icons. */
export function Empty({ icon = 'info', title, children, command, action }: { icon?: SetIconName; title: string; children?: ReactNode; command?: string; action?: ReactNode }) {
  return (
    <div className="om-empty" role="note">
      <span className="om-empty-icon">
        <SetIcon name={icon} size={28} />
      </span>
      <p className="om-empty-title">{title}</p>
      {children && <div className="om-empty-body">{children}</div>}
      {command && (
        <p className="om-empty-cmd">
          <span className="om-visually-hidden">Or from a terminal: </span>
          <code>{command}</code>
        </p>
      )}
      {action && <div className="om-empty-action">{action}</div>}
    </div>
  );
}

/* ---------- layout pieces ---------- */

/** A titled group of rows inside a section, like an iOS/umbrelOS settings card. */
export function Group({ title, description, aside, children, id }: { title: string; description?: ReactNode; aside?: ReactNode; children: ReactNode; id?: string }) {
  const hid = useId();
  return (
    <section className="om-set-group" aria-labelledby={id ?? hid}>
      <header className="om-set-group-head">
        <div>
          <h3 id={id ?? hid}>{title}</h3>
          {description && <p className="om-set-group-desc">{description}</p>}
        </div>
        {aside && <div className="om-set-group-aside">{aside}</div>}
      </header>
      <div className="om-set-group-body">{children}</div>
    </section>
  );
}

/** One row: leading icon, title, description, and a trailing value or control. */
export function Row({ icon, title, description, meta, trailing, tone }: { icon?: SetIconName; title: ReactNode; description?: ReactNode; meta?: ReactNode; trailing?: ReactNode; tone?: Tone }) {
  return (
    <div className="om-set-row">
      {icon && (
        <span className={cx('om-set-row-icon', tone && `om-tone-${tone}`)}>
          <SetIcon name={icon} size={18} />
        </span>
      )}
      <div className="om-set-row-main">
        <div className="om-set-row-title">{title}</div>
        {description && <div className="om-set-row-desc">{description}</div>}
        {meta && <div className="om-set-meta">{meta}</div>}
      </div>
      {trailing && <div className="om-set-row-trail">{trailing}</div>}
    </div>
  );
}

/** A list of rows; `label` names the list for screen readers. */
export function Rows({ label, children }: { label: string; children: ReactNode }) {
  return (
    <ul className="om-set-rows" aria-label={label}>
      {Children.toArray(children).map((c, i) => (
        <li key={i}>{c}</li>
      ))}
    </ul>
  );
}

/**
 * A switch that shows the hub's value, not an optimistic one. Flipping it creates a request
 * (or an instant call); the value changes when the hub reports it changed.
 */
export function Switch({ checked, label, onToggle, disabled, describedBy }: { checked: boolean; label: string; onToggle: () => void; disabled?: boolean; describedBy?: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} aria-label={label} aria-describedby={describedBy} className="om-set-switch" disabled={disabled} onClick={onToggle}>
      <span className="om-set-switch-thumb" aria-hidden="true" />
    </button>
  );
}

/** The CLI and API calls behind a section (P4: every UI action maps to a call). */
export function CallHint({ calls }: { calls: string[] }) {
  return (
    <details className="om-details om-set-calls">
      <summary>Same thing from a terminal or the API</summary>
      <pre className="om-code">{calls.join('\n')}</pre>
    </details>
  );
}

/** Section title block at the top of a settings page. */
export function SectionHead({ icon, title, lede, aside }: { icon: SetIconName; title: string; lede: ReactNode; aside?: ReactNode }) {
  return (
    <header className="om-set-head">
      <span className="om-set-head-icon" aria-hidden="true">
        <SetIcon name={icon} size={22} />
      </span>
      <div className="om-set-head-text">
        <h2 className="om-set-title">{title}</h2>
        <p className="om-set-lede">{lede}</p>
      </div>
      {aside && <div className="om-set-head-aside">{aside}</div>}
    </header>
  );
}

/** QR modules from the gateway as an SVG. The code below it is the fallback for people who cannot scan. */
export function QrCode({ modules, label }: { modules: number[][]; label: string }) {
  const n = modules.length;
  return (
    <svg className="om-set-qr" viewBox={`-2 -2 ${n + 4} ${n + 4}`} role="img" aria-label={label} shapeRendering="crispEdges">
      <rect x={-2} y={-2} width={n + 4} height={n + 4} className="om-set-qr-bg" />
      {modules.flatMap((row, y) => row.map((m, x) => (m ? <rect key={`${x}-${y}`} x={x} y={y} width={1} height={1} className="om-set-qr-on" /> : null)))}
    </svg>
  );
}

/** A small stat: label, value, and an optional pill. */
export function Fact({ label, value, pill }: { label: string; value: ReactNode; pill?: ReactNode }) {
  return (
    <div className="om-set-fact">
      <span className="om-set-fact-label">{label}</span>
      <span className="om-set-fact-value">{value}</span>
      {pill}
    </div>
  );
}
