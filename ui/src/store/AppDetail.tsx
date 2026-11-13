// SPDX-License-Identifier: Apache-2.0
// App page (IA §2.3, TAXONOMY §3-4, PU-07, PU-11): hero, screenshots, trust, requirements with the
// hub's placement verdict, permissions, release notes, and the install request with live progress.
import { useId, useRef, useState } from 'react';
import { Button } from '../components/Button';
import { Card } from '../components/Card';
import { EmptyState } from '../components/EmptyState';
import { Icon } from '../components/Icon';
import { Meter } from '../components/Meter';
import { StatusPill } from '../components/StatusPill';
import { cx } from '../lib/cx';
import { formatAgo, formatDay, secondsSince } from '../lib/time';
import { installBlockReason, safeHttpUrl } from '../lib/trust';
import { AppTile, ClassPills, LoadGate, Skeleton } from './bits';
import { CategoryIcon } from './CategoryIcon';
import { JobProgress } from './Jobs';
import { formatMb, isJobActive, primaryAction } from './logic';
import { CATEGORY_BY_SLUG, DEPLOY_CLASSES, DEVICE_LABEL, EXPOSURE_LABEL, LICENCE_CLASSES } from './taxonomy';
import type { AppPlan, CatalogApp, LoadState, Screenshot, StoreJob } from './types';

// ---------------------------------------------------------------- screenshots

export function Screenshots({ shots, appName }: { shots: Screenshot[]; appName: string }) {
  const [at, setAt] = useState(0);
  const list = useRef<HTMLUListElement>(null);
  const id = useId();
  if (shots.length === 0)
    return (
      <div className="om-store-shots-empty">
        <CategoryIcon name="grid" />
        <p>No screenshots published for {appName} yet. They come from the app's Market entry.</p>
      </div>
    );
  const go = (n: number) => {
    const k = (n + shots.length) % shots.length;
    setAt(k);
    const el = list.current?.children[k] as HTMLElement | undefined;
    el?.scrollIntoView?.({ behavior: 'smooth', inline: 'start', block: 'nearest' });
  };
  return (
    <section className="om-store-shots" aria-roledescription="carousel" aria-labelledby={id}>
      <h2 id={id} className="om-visually-hidden">
        Screenshots of {appName}
      </h2>
      <ul ref={list} className="om-store-shots-list">
        {shots.map((s, k) => {
          const src = s.src && (s.src.startsWith('/') ? s.src : safeHttpUrl(s.src));
          return (
            <li key={k} aria-roledescription="slide" aria-label={`${k + 1} of ${shots.length}`} aria-current={k === at ? 'true' : undefined}>
              {src ? (
                <img src={src} alt={s.alt} loading="lazy" />
              ) : (
                <div className={cx('om-store-shot-art', `om-store-shot-art-${k % 3}`)} role="img" aria-label={`Placeholder for: ${s.alt}`}>
                  <span className="om-store-shot-bar" />
                  <span className="om-store-shot-side" />
                  <span className="om-store-shot-main" />
                  <span className="om-store-shot-cap">Illustration · not a real screenshot</span>
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {shots.length > 1 && (
        <div className="om-store-shots-nav">
          <button type="button" className="om-icon-btn" aria-label="Previous screenshot" onClick={() => go(at - 1)}>
            <CategoryIcon name="chevronLeft" />
          </button>
          <span className="om-hint" aria-live="polite">
            {at + 1} / {shots.length}
          </span>
          <button type="button" className="om-icon-btn" aria-label="Next screenshot" onClick={() => go(at + 1)}>
            <Icon name="chevron" />
          </button>
        </div>
      )}
    </section>
  );
}

// ---------------------------------------------------------------- trust

/** Trust card with deployment class, licence class, scan facts and links (§9.3, §11.1, §11.4). */
export function StoreTrustCard({ app, now }: { app: CatalogApp; now: number }) {
  const cls = DEPLOY_CLASSES[app.deploy_class];
  const listOnly = app.deploy_class === 'list-only';
  const block = listOnly || app.deploy_class === 'core' ? undefined : installBlockReason(app.scan, app.tier, now);
  const scan = app.scan;
  const scanAge = scan ? secondsSince(scan.scanned_at, now) : Number.NaN;
  const links = (['docs', 'github', 'website', 'support'] as const)
    .map((k) => [k, safeHttpUrl(app.links?.[k])] as const)
    .filter((x): x is readonly [(typeof x)[0], string] => x[1] !== undefined);
  return (
    <Card
      title="Trust"
      level={2}
      variant={block ? 'attention' : 'default'}
      aside={<ClassPills app={app} />}
      className="om-store-trust"
    >
      <p className="om-store-trust-lead" aria-live="polite">
        <Icon name={block ? 'alert' : 'approvals'} />
        <span>{block ?? (listOnly ? (app.list_only_reason ?? cls.sentence) : cls.sentence)}</span>
      </p>
      {app.deploy_class === 'market-community' && app.community_gaps?.length ? (
        <p className="om-note om-tone-neutral">Not fully checked by OneMind: {app.community_gaps.join('; ')}.</p>
      ) : null}
      <dl className="om-facts">
        <div>
          <dt>Licence</dt>
          <dd>
            {app.license || 'unknown'}
            {app.licence_class && (
              <span className="om-hint">
                {' '}
                · {LICENCE_CLASSES[app.licence_class].label} ({app.licence_class})
              </span>
            )}
          </dd>
        </div>
        {!listOnly && (
          <div>
            <dt>Last scan</dt>
            <dd>
              {scan ? (
                <>
                  {formatDay(scan.scanned_at)} <span className="om-hint">({formatAgo(scanAge)})</span>{' '}
                  <StatusPill tone={scan.result === 'pass' ? 'ok' : 'bad'} label={scan.result === 'pass' ? 'Passed' : 'Failed'} />
                </>
              ) : (
                'Never scanned'
              )}
            </dd>
          </div>
        )}
        {scan && (scan.critical !== undefined || scan.high !== undefined) && (
          <div>
            <dt>Vulnerabilities</dt>
            <dd>
              {scan.critical ?? 0} critical · {scan.high ?? 0} high
            </dd>
          </div>
        )}
        {scan?.malware !== undefined && (
          <div>
            <dt>Malware scan</dt>
            <dd>{scan.malware === 0 ? 'Clean' : `${scan.malware} finding(s)`}</dd>
          </div>
        )}
        {scan?.cosign && (
          <div>
            <dt>Image signature</dt>
            <dd>{scan.cosign === 'verified' ? 'Verified' : scan.cosign === 'unsigned' ? 'Not signed upstream' : 'Failed'}</dd>
          </div>
        )}
        {scan?.smoke && (
          <div>
            <dt>Smoke test</dt>
            <dd>{scan.smoke === 'pass' ? 'Passed' : scan.smoke === 'skipped' ? 'Skipped' : 'Failed'}</dd>
          </div>
        )}
        {app.upstream && (
          <div>
            <dt>Upstream release</dt>
            <dd>
              {app.upstream.release} · {formatDay(app.upstream.released_at)}
              {app.upstream.archived && ' · archived'}
            </dd>
          </div>
        )}
      </dl>
      {links.length > 0 && (
        <ul className="om-store-links" aria-label={`Links for ${app.name}`}>
          {links.map(([k, href]) => (
            <li key={k}>
              <a href={href} target="_blank" rel="noreferrer noopener">
                <Icon name={k === 'github' ? 'link' : k === 'support' ? 'info' : 'external'} size={16} />
                {k === 'github' ? 'Source' : k[0]!.toUpperCase() + k.slice(1)}
                <span className="om-visually-hidden"> (opens in a new tab)</span>
              </a>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- requirements and placement

export function Requirements({ app, plan, planState, now }: { app: CatalogApp; plan?: AppPlan; planState: LoadState; now: number }) {
  const p = app.placement;
  const facts: [string, string][] = [
    ['Runs on', !p?.roles || p.roles.includes('any') ? 'Any node' : p.roles.map((r) => (r === 'hub' ? 'The hub' : r === 'worker' ? 'A worker node' : 'A leaf')).join(', ')],
    ['Architectures', app.archs.join(', ') || 'none published'],
    ['Memory', app.requires?.minMemoryMb ? `At least ${formatMb(app.requires.minMemoryMb)}` : 'Not stated'],
    ['GPU', app.requires?.gpu || p?.gpu === 'required' ? 'Needs a GPU' : p?.gpu === 'optional' ? 'Faster with a GPU' : 'Not needed'],
  ];
  if (p?.devices?.length) facts.push(['Devices', p.devices.map((d) => DEVICE_LABEL[d.class]).join(', ')]);
  if (app.storage?.data) facts.push(['Storage', `${app.storage.data.size}, ${app.storage.data.backup ? 'backed up' : 'not backed up'}`]);
  facts.push(['Reachable on', EXPOSURE_LABEL.lan + (p?.exposure && p.exposure !== 'lan' ? `; can be widened to ${p.exposure} by a separate request` : '')]);
  if (app.updates) facts.push(['Updates', app.updates.channel === 'security' ? 'Security fixes only' : 'Stable releases' + (app.updates.automerge === 'patch' ? '; patches install in your window' : '; each waits for you')]);

  const fitting = plan?.nodes.filter((n) => n.fits) ?? [];
  const chosen = plan?.nodes.find((n) => n.chosen) ?? fitting[0];
  const verdict = !plan ? null : fitting.length === 0 ? 'none' : chosen?.stale ? 'stale' : 'fits';
  return (
    <Card title="Requirements and fit" level={2}>
      <dl className="om-facts">
        {facts.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      {app.deploy_class === 'list-only' ? (
        <p className="om-hint">OneMind does not place list-only apps.</p>
      ) : (
        <LoadGate state={planState} now={now} what="placement plan" skeleton={<Skeleton tile={false} lines={3} />}>
          {plan && (
            <div className={cx('om-store-verdict', `om-tone-${verdict === 'fits' ? 'ok' : verdict === 'stale' ? 'warn' : 'bad'}`)} aria-live="polite">
              <Icon name={verdict === 'fits' ? 'check' : verdict === 'stale' ? 'clock' : 'x'} />
              <div>
                <p className="om-store-verdict-title">
                  {verdict === 'fits' && (
                    <>
                      Fits on <strong>{chosen!.node}</strong>
                    </>
                  )}
                  {verdict === 'stale' && (
                    <>
                      Fits, but <strong>{chosen!.node}</strong> is stale
                      {chosen!.last_seen ? ` (last report ${formatAgo(secondsSince(chosen!.last_seen, now))})` : ''}
                    </>
                  )}
                  {verdict === 'none' && 'No node can run this'}
                </p>
                <ul className="om-store-nodefit">
                  {plan.nodes.map((n) => (
                    <li key={n.node}>
                      <span className="om-store-nodefit-name">
                        <Icon name={n.fits ? 'check' : 'x'} size={14} />
                        {n.node}
                        {n.stale && <StatusPill tone="warn" label="Stale" />}
                      </span>
                      <span className="om-hint">{n.reasons.join(' · ')}</span>
                      {n.mem_free_mb !== undefined && n.mem_total_mb && (
                        <Meter
                          label={`Memory in use on ${n.node}`}
                          value={n.mem_total_mb - n.mem_free_mb}
                          max={n.mem_total_mb}
                          valueText={`${formatMb(n.mem_free_mb)} free of ${formatMb(n.mem_total_mb)}`}
                          stale={n.stale}
                        />
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
        </LoadGate>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------- page

export interface AppDetailProps {
  app?: CatalogApp;
  state: LoadState;
  plan?: AppPlan;
  planState: LoadState;
  job?: StoreJob;
  now: number;
  backHref: string;
  onRequestInstall: (app: CatalogApp) => void;
  onOpen: (app: CatalogApp) => void;
  manageHref?: (id: string) => string;
  onRetry?: () => void;
}

export function AppDetail({ app, state, plan, planState, job, now, backHref, onRequestInstall, onOpen, manageHref, onRetry }: AppDetailProps) {
  const whyId = useId();
  return (
    <div className="om-store om-store-detail">
      <a className="om-store-back" href={backHref}>
        <CategoryIcon name="chevronLeft" size={16} /> Market
      </a>
      <LoadGate
        state={state}
        now={now}
        what="app"
        onRetry={onRetry}
        skeleton={
          <div className="om-store-detail-hero">
            <Skeleton lines={3} />
          </div>
        }
      >
        {!app ? (
          <EmptyState icon="search" title="No such app" command="onemind apps list">
            <p>The Market has no app with this id. It may have been removed from the index.</p>
          </EmptyState>
        ) : (
          (() => {
            const action = primaryAction(app, now);
            const stale = state.kind === 'ready' && state.stale;
            const busy = job && isJobActive(job.state);
            const reason = stale
              ? 'The hub is not answering. Requests wait until it is back.'
              : action.kind === 'blocked' || action.kind === 'none'
                ? action.reason
                : busy
                  ? 'A request for this app is already in progress.'
                  : undefined;
            const cat = CATEGORY_BY_SLUG[app.category];
            const notes = app.release_notes ?? [];
            return (
              <>
                <header className="om-store-detail-hero">
                  <AppTile app={app} size={96} />
                  <div className="om-store-detail-titles">
                    <h1 className="om-store-detail-name">{app.name}</h1>
                    <p className="om-store-detail-tagline">{app.tagline ?? app.description}</p>
                    <p className="om-store-detail-meta">
                      <span className="om-store-catchip">
                        {cat && <CategoryIcon name={cat.icon} size={14} />}
                        {cat?.label}
                      </span>
                      {(app.tags ?? []).map((t) => (
                        <span key={t} className="om-store-tag">
                          #{t}
                        </span>
                      ))}
                      <span className="om-hint">Version {app.version}</span>
                    </p>
                    <ClassPills app={app} />
                  </div>
                  <div className="om-store-detail-cta">
                    {action.kind === 'open' ? (
                      <>
                        <Button variant="primary" icon="external" onClick={() => onOpen(app)}>
                          Open
                        </Button>
                        {manageHref && (
                          <a className="om-btn om-btn-secondary" href={manageHref(app.id)}>
                            Manage
                          </a>
                        )}
                      </>
                    ) : action.kind === 'upstream' ? (
                      action.href && (
                        <a className="om-btn om-btn-primary" href={action.href} target="_blank" rel="noreferrer noopener">
                          Get it upstream <Icon name="external" size={16} />
                          <span className="om-visually-hidden"> (opens in a new tab)</span>
                        </a>
                      )
                    ) : (
                      <Button
                        variant="primary"
                        icon="plus"
                        disabled={!!reason}
                        aria-describedby={reason ? whyId : undefined}
                        onClick={() => onRequestInstall(app)}
                      >
                        {action.kind === 'request-deploy' ? 'Request deploy' : 'Request install'}
                        <span className="om-visually-hidden"> {app.name}</span>
                      </Button>
                    )}
                    {reason && (
                      <p id={whyId} className="om-store-cta-why">
                        {reason}
                      </p>
                    )}
                    {!reason && action.kind === 'request-install' && <p className="om-hint">An owner approves it first.</p>}
                  </div>
                </header>

                {job && <JobProgress job={job} now={now} onOpen={() => onOpen(app)} />}

                <Screenshots shots={app.gallery ?? []} appName={app.name} />

                <div className="om-store-detail-cols">
                  <div className="om-store-col">
                    <Card title="About" level={2}>
                      <p>{app.description}</p>
                    </Card>
                    <Card title="What's new" level={2} subtitle={notes[0] ? `${notes[0].version} · ${formatDay(notes[0].released_at)}` : undefined}>
                      {notes.length === 0 ? (
                        <p className="om-hint">No release notes published for this version.</p>
                      ) : (
                        <ReleaseNotes notes={notes} />
                      )}
                    </Card>
                    <Requirements app={app} plan={plan} planState={planState} now={now} />
                    {app.permissions?.length || app.extensions?.length ? (
                      <Card title="Permissions" level={2} subtitle="What it asks for, in plain words. Agents never see its credentials.">
                        {app.permissions?.length ? (
                          <>
                            <h3 className="om-subhead">It will be able to</h3>
                            <ul className="om-store-perms">
                              {app.permissions.map((p) => (
                                <li key={p}>
                                  <Icon name="check" size={16} />
                                  {p}
                                </li>
                              ))}
                            </ul>
                          </>
                        ) : null}
                        {app.plugin && app.extensions?.length ? (
                          <>
                            <h3 className="om-subhead">It adds to OneMind</h3>
                            <ul className="om-store-perms om-store-perms-agent">
                              {app.extensions.map((p) => (
                                <li key={p}>
                                  <Icon name="agent" size={16} />
                                  {p}
                                </li>
                              ))}
                            </ul>
                          </>
                        ) : null}
                      </Card>
                    ) : null}
                  </div>
                  <div className="om-store-col">
                    <StoreTrustCard app={app} now={now} />
                  </div>
                </div>
              </>
            );
          })()
        )}
      </LoadGate>
    </div>
  );
}

export function ReleaseNotes({ notes, limit = 3 }: { notes: CatalogApp['release_notes'] & object; limit?: number }) {
  return (
    <ol className="om-store-notes">
      {notes.slice(0, limit).map((n) => {
        const href = safeHttpUrl(n.url);
        return (
          <li key={n.version}>
            <p className="om-store-notes-head">
              <strong>{n.version}</strong> <span className="om-hint">{formatDay(n.released_at)}</span>
            </p>
            <ul>
              {n.notes.map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
            {href && (
              <a href={href} target="_blank" rel="noreferrer noopener">
                Full changelog<span className="om-visually-hidden"> for {n.version} (opens in a new tab)</span>
              </a>
            )}
          </li>
        );
      })}
    </ol>
  );
}
