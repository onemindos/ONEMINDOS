// SPDX-License-Identifier: Apache-2.0
// Host frame for every Home widget (COMPONENTS.md "Widget frame"): title, size, and the
// loading / error / empty / stale states, so no widget can fail silently or look live
// when it is not (P2). A broken widget shows a fallback and never blocks Home.
import { useId, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { Icon, type IconName } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import type { WidgetSize } from './layout';

export type WidgetBodyState =
  | { kind: 'ready' }
  | { kind: 'loading' }
  | { kind: 'error'; error: string; message: string }
  | { kind: 'empty'; title: string; body?: string };

export interface WidgetFrameProps {
  title: string;
  icon?: IconName;
  /** Custom glyph instead of an icon (app widgets show the app). */
  glyph?: ReactNode;
  size: WidgetSize;
  /** Where "Open" goes. */
  href?: string;
  hrefLabel?: string;
  state?: WidgetBodyState;
  /** Last report, not live: the frame is dashed; `detail` says from when (empty when a page banner says it). */
  stale?: { label: string; detail: string } | null;
  /** Data source for the headless equivalent (P4), shown in edit mode. */
  source?: string;
  showSource?: boolean;
  /** Right of the title, e.g. a count pill. */
  aside?: ReactNode;
  children?: ReactNode;
}

export function WidgetFrame({ title, icon, glyph, size, href, hrefLabel = 'Open', state = { kind: 'ready' }, stale, source, showSource, aside, children }: WidgetFrameProps) {
  const id = useId();
  return (
    <section className={cx('omh-widget', `omh-size-${size}`, stale && 'omh-widget-stale')} aria-labelledby={id} aria-busy={state.kind === 'loading' || undefined}>
      <header className="omh-widget-head">
        <span className="omh-widget-icon">{glyph ?? (icon ? <Icon name={icon} size={18} /> : null)}</span>
        <h3 id={id} className="omh-widget-title">
          {title}
        </h3>
        {(stale || aside) && (
          <span className="omh-widget-meta">
            {stale && <StatusPill tone="warn" label={stale.label} />}
            {aside}
          </span>
        )}
        {href && (
          <a className="omh-widget-link" href={href} title={`${hrefLabel} ${title}`}>
            <span className="omh-widget-link-text">{hrefLabel}</span>
            <span className="om-visually-hidden"> {title}</span>
            <Icon name="chevron" size={14} />
          </a>
        )}
      </header>
      {stale?.detail && <p className="omh-stale-note">{stale.detail}</p>}
      <div className="omh-widget-body">
        {state.kind === 'loading' && (
          <div className="omh-skeleton" role="status">
            <span className="om-visually-hidden">Loading {title}</span>
            <span className="omh-skel omh-skel-lg" />
            <span className="omh-skel" />
            <span className="omh-skel omh-skel-sm" />
          </div>
        )}
        {state.kind === 'error' && (
          <div className="omh-widget-error" role="alert">
            <StatusPill tone="bad" label="Could not load" />
            <p>{state.message}</p>
            <code className="omh-code">{state.error}</code>
          </div>
        )}
        {state.kind === 'empty' && (
          <div className="omh-widget-empty">
            <p className="omh-empty-title">{state.title}</p>
            {state.body && <p className="om-hint">{state.body}</p>}
          </div>
        )}
        {state.kind === 'ready' && children}
      </div>
      {showSource && source && (
        <p className="omh-source">
          <span className="om-visually-hidden">Same data without the UI: </span>
          <code title={source}>{source}</code>
          <button
            type="button"
            className="omh-source-copy"
            onClick={() => {
              void navigator.clipboard?.writeText(source).catch(() => undefined);
            }}
          >
            Copy<span className="om-visually-hidden"> the call for {title}</span>
          </button>
        </p>
      )}
    </section>
  );
}
