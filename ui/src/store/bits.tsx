// SPDX-License-Identifier: Apache-2.0
// Small store building blocks: app tile, class pills, fit line, skeletons, load gate, tabs.
// Every store component imports this file, so the store styles load with it.
import './store.css';
import { useId, useRef, useState, type KeyboardEvent, type ReactNode } from 'react';
import { Button } from '../components/Button';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { formatAgo, secondsSince } from '../lib/time';
import { AppIcon } from '../components/AppIcon';
import { DEPLOY_CLASSES } from './taxonomy';
import type { CatalogApp, FitSummary, LoadState } from './types';

/** The app's icon tile: the shared AppIcon (CRITIQUE #20), kept under its store name. */
export function AppTile({ app, size = 48 }: { app: Pick<CatalogApp, 'id' | 'name' | 'icon'>; size?: number }) {
  return <AppIcon app={app} size={size} />;
}

/** Deployment class pill, plus "Plugin" and "Blocked" when they apply (TAXONOMY §2). */
export function ClassPills({ app }: { app: Pick<CatalogApp, 'deploy_class' | 'plugin' | 'tier'> }) {
  const c = DEPLOY_CLASSES[app.deploy_class];
  return (
    <span className="om-store-pills">
      <StatusPill tone={c.tone} label={c.label} dot={app.deploy_class === 'market-verified'} className={app.deploy_class === 'private' ? 'om-store-pill-private' : undefined} />
      {/* Violet is reserved for agents (PRINCIPLES P3); a plugin is not one. */}
      {app.plugin && <StatusPill tone="info" label="Plugin" dot={false} />}
      {app.tier === 'blocked' && <StatusPill tone="bad" label="Blocked" />}
    </span>
  );
}

/** One line: where it would run, or why it cannot (TAXONOMY §3.3). The hub's verdict, rendered. */
export function FitLine({ fit, listOnly }: { fit?: FitSummary; listOnly?: boolean }) {
  if (listOnly) return <span className="om-store-fit om-tone-neutral">Not installed by OneMind</span>;
  if (!fit) return <span className="om-store-fit om-tone-neutral">Fit unknown</span>;
  const icon = fit.verdict === 'fits' ? 'check' : fit.verdict === 'stale' ? 'clock' : 'x';
  const tone = fit.verdict === 'fits' ? 'ok' : fit.verdict === 'stale' ? 'warn' : 'bad';
  const text =
    fit.verdict === 'fits'
      ? `Fits on ${fit.node ?? 'a node'}`
      : fit.verdict === 'stale'
        ? `Fits on ${fit.node ?? 'a node'}, but it is stale`
        : `No node fits${fit.reason ? `: ${fit.reason}` : ''}`;
  return (
    <span className={cx('om-store-fit', `om-tone-${tone}`)}>
      <Icon name={icon} size={16} />
      <span>{text}</span>
    </span>
  );
}

export function Skeleton({ lines = 3, tile = true }: { lines?: number; tile?: boolean }) {
  return (
    <div className="om-store-skel" aria-hidden="true">
      {tile && <span className="om-store-skel-tile" />}
      <span className="om-store-skel-lines">
        {Array.from({ length: lines }, (_, i) => (
          <span key={i} className="om-store-skel-line" style={{ width: `${90 - i * 18}%` }} />
        ))}
      </span>
    </div>
  );
}

/**
 * Renders loading, error and stale states around `children` (IA §4). Loading shows a skeleton and a
 * screen-reader status; error shows the contract code; stale keeps the content with a dashed banner.
 */
export function LoadGate({
  state,
  now,
  what,
  onRetry,
  skeleton,
  children,
}: {
  state: LoadState;
  now: number;
  what: string;
  onRetry?: () => void;
  skeleton?: ReactNode;
  children: ReactNode;
}) {
  if (state.kind === 'loading')
    return (
      <div className="om-store-loading">
        <p role="status" className="om-visually-hidden">
          Loading {what}
        </p>
        {skeleton ?? (
          <div className="om-store-grid">
            {[0, 1, 2, 3, 4, 5].map((i) => (
              <div key={i} className="om-store-card om-store-card-skel">
                <Skeleton />
              </div>
            ))}
          </div>
        )}
      </div>
    );
  if (state.kind === 'error')
    return (
      <div role="alert">
        <EmptyState icon="alert" title={`Could not load ${what}`} action={onRetry && <Button onClick={onRetry}>Try again</Button>}>
          <p>
            The hub answered <code>{state.code}</code>: {state.message}
          </p>
        </EmptyState>
      </div>
    );
  return (
    <>
      {state.stale && <StaleBanner fetchedAt={state.fetched_at} now={now} what={what} />}
      {children}
    </>
  );
}

export function StaleBanner({ fetchedAt, now, what }: { fetchedAt: string; now: number; what: string }) {
  return (
    <div className="om-store-banner om-tone-warn" role="status">
      <Icon name="clock" />
      <p>
        <strong>Last known {what}</strong>, from {formatAgo(secondsSince(fetchedAt, now))}. The hub is not answering, so this is not live and nothing can be
        requested until it is back.
      </p>
    </div>
  );
}

export interface TabDef {
  id: string;
  label: string;
  badge?: number;
  content: ReactNode;
}

/** WAI-ARIA tabs: arrow keys move between tabs, Home and End jump, Tab moves into the panel. */
export function Tabs({ tabs, label, initial, onChange }: { tabs: TabDef[]; label: string; initial?: string; onChange?: (id: string) => void }) {
  const [current, setCurrent] = useState(initial ?? tabs[0]?.id);
  const base = useId();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const select = (id: string, focus = false) => {
    setCurrent(id);
    onChange?.(id);
    if (focus) refs.current[id]?.focus();
  };
  const onKey = (e: KeyboardEvent) => {
    const i = tabs.findIndex((t) => t.id === current);
    const next =
      e.key === 'ArrowRight' ? (i + 1) % tabs.length : e.key === 'ArrowLeft' ? (i - 1 + tabs.length) % tabs.length : e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : -1;
    if (next < 0) return;
    e.preventDefault();
    select(tabs[next]!.id, true);
  };
  return (
    <div className="om-store-tabs">
      <div role="tablist" aria-label={label} className="om-store-tablist" onKeyDown={onKey}>
        {tabs.map((t) => (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`${base}-tab-${t.id}`}
            aria-selected={current === t.id}
            aria-controls={`${base}-panel-${t.id}`}
            tabIndex={current === t.id ? 0 : -1}
            className="om-store-tab"
            onClick={() => select(t.id)}
          >
            {t.label}
            {t.badge ? (
              <span className="om-store-count" aria-label={`${t.badge} waiting`}>
                {t.badge}
              </span>
            ) : null}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          role="tabpanel"
          id={`${base}-panel-${t.id}`}
          aria-labelledby={`${base}-tab-${t.id}`}
          hidden={current !== t.id}
          tabIndex={0}
          className="om-store-tabpanel"
        >
          {current === t.id && t.content}
        </div>
      ))}
    </div>
  );
}

/** "Exact request and API equivalent" disclosure (PRINCIPLES P3, P4). */
export function RequestDetails({ api, cli, proposed }: { api: string; cli: string; proposed: boolean }) {
  return (
    <details className="om-details">
      <summary>Exact request and API equivalent</summary>
      <pre className="om-code">{api}</pre>
      <p className="om-hint">
        CLI (planned): <code>{cli}</code>
      </p>
      {proposed && <p className="om-hint">This action type is proposed for the contract (PD-03); today the gateway accepts install and remove.</p>}
    </details>
  );
}
