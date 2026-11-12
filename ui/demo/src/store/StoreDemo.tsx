// SPDX-License-Identifier: Apache-2.0
// Demo of the App Store (ui/src/store): #/store, #/store/app/<id>, #/store/installed,
// #/store/updates, #/store/manage/<id>[/<tab>], #/store/states. Fixtures only, frozen clock.
// `?state=loading|error|stale|empty` shows the load states on any of these screens.
import { useEffect, useState } from 'react';
import {
  AppDetail,
  Button,
  InstalledList,
  InstallReview,
  JobsTray,
  ManageApp,
  Market,
  nextJobState,
  PageHeader,
  useToast,
  type CatalogApp,
  type InstalledApp,
  type LoadState,
  type StoreActionRequest,
  type StoreJob,
} from '../../../src';
import { catalog, collections, featured, installed, jobs as seedJobs, logs, NOW, planFor, byId } from './fixtures';

const READY: LoadState = { kind: 'ready', fetched_at: new Date(NOW - 2000).toISOString() };

function demoState(): { state: LoadState; empty: boolean } {
  const s = new URLSearchParams(window.location.search).get('state');
  if (s === 'loading') return { state: { kind: 'loading' }, empty: false };
  if (s === 'error') return { state: { kind: 'error', code: 'unauthenticated', message: 'Your session ended. Sign in again.' }, empty: false };
  if (s === 'stale') return { state: { kind: 'ready', fetched_at: new Date(NOW - 260_000).toISOString(), stale: true }, empty: false };
  return { state: READY, empty: s === 'empty' };
}

function parts(): string[] {
  return window.location.hash.replace(/^#\/?/, '').split('/').slice(1);
}

const href = {
  market: '#/store',
  app: (id: string) => `#/store/app/${id}`,
  installed: '#/store/installed',
  updates: '#/store/updates',
  manage: (id: string) => `#/store/manage/${id}`,
};

export function StoreDemo() {
  const [p, setP] = useState(parts);
  const [jobs, setJobs] = useState<StoreJob[]>(seedJobs);
  const [review, setReview] = useState<CatalogApp | null>(null);
  const toast = useToast();
  const { state, empty } = demoState();
  useEffect(() => {
    const on = () => setP(parts());
    window.addEventListener('hashchange', on);
    return () => window.removeEventListener('hashchange', on);
  }, []);

  const view = p[0] ?? '';
  const open = (name: string) => toast.show({ tone: 'info', title: `Opening ${name}`, body: 'In the demo nothing opens; on a box this is the app URL behind the OneMind sign-in.' });
  const request = (req: StoreActionRequest) => {
    const id = `act-${Math.random().toString(16).slice(2, 6)}`;
    const app = byId(req.params.app_id);
    if (req.type === 'app.install' || req.type === 'app.update')
      setJobs((j) => [{ action_id: id, app_id: req.params.app_id, app_name: app?.name ?? req.params.app_id, type: req.type, state: 'awaiting_approval', updated_at: new Date(NOW).toISOString(), requested_by: 'you' }, ...j]);
    toast.show({ tone: 'info', title: `${req.summary}: requested`, body: 'It is waiting in Approvals.', action: { label: 'View', onClick: () => (window.location.hash = '#/approvals') } });
  };
  /** Demo only: play the approval and the executor's steps so the progress UI can be seen. */
  const simulate = (actionId: string, healthy = true) => {
    const tick = () =>
      setJobs((js) => {
        const j = js.find((x) => x.action_id === actionId);
        if (!j) return js;
        const next = nextJobState(j.state, healthy);
        if (next !== j.state) window.setTimeout(tick, next === 'pulling' ? 1600 : 1300);
        return js.map((x) => (x.action_id === actionId ? { ...x, state: next, percent: next === 'pulling' ? 35 : next === 'starting' ? 50 : undefined } : x));
      });
    tick();
  };
  const demoJob = jobs.find((j) => j.requested_by === 'you' && j.state === 'awaiting_approval');

  const apps = empty ? [] : catalog;
  const inst: InstalledApp[] = empty ? [] : installed;
  const nUpdates = inst.filter((i) => i.update && i.update.version !== i.app.version).length;

  const nav = (
    <nav aria-label="App Store" className="d-row">
      {[
        { id: '', label: 'Discover', h: href.market },
        { id: 'installed', label: `Installed (${inst.length})`, h: href.installed },
        { id: 'updates', label: nUpdates ? `Updates (${nUpdates})` : 'Updates', h: href.updates },
      ].map((t) => (
        <a key={t.id} href={t.h} className="d-chip" aria-current={view === t.id || (t.id === '' && view === 'app') ? 'page' : undefined} style={{ textDecoration: 'none' }}>
          {t.label}
        </a>
      ))}
    </nav>
  );

  let body;
  if (view === 'app') {
    const app = byId(p[1] ?? '');
    body = (
      <AppDetail
        app={app}
        state={state}
        plan={app ? planFor(app.id) : undefined}
        planState={state.kind === 'ready' ? READY : state}
        job={jobs.find((j) => j.app_id === app?.id)}
        now={NOW}
        backHref={href.market}
        manageHref={href.manage}
        onRequestInstall={setReview}
        onOpen={(a) => open(a.name)}
      />
    );
  } else if (view === 'manage') {
    const i = inst.find((x) => x.app.id === p[1]);
    body = (
      <ManageApp
        inst={i}
        state={state}
        now={NOW}
        isOwner
        job={jobs.find((j) => j.app_id === i?.app.id)}
        logs={logs}
        logState={READY}
        backHref={href.installed}
        storeHref={href.app}
        initialTab={p[2]}
        onOpen={(x) => open(x.app.name)}
        onRequest={request}
        onCopied={(label) => toast.show({ tone: 'ok', title: `${label} copied` })}
      />
    );
  } else if (view === 'installed' || view === 'updates') {
    body = (
      <>
        <PageHeader title={view === 'updates' ? 'Updates' : 'Installed apps'} lede="Every change is a request: an owner approves it first, and updates revert on their own if the app is not healthy afterwards." />
        {nav}
        <InstalledList apps={inst} state={state} now={NOW} jobs={jobs} view={view === 'updates' ? 'updates' : 'all'} manageHref={href.manage} onOpen={(x) => open(x.app.name)} onRequest={request} />
      </>
    );
  } else {
    body = (
      <>
        <PageHeader
          title="App Store"
          lede="Sixteen categories, each app checked for licence, vulnerabilities and malware. Installing asks for approval first."
          actions={<Button icon="plus">Deploy your own</Button>}
        />
        {nav}
        <Market
          apps={apps}
          state={state}
          now={NOW}
          collections={collections}
          featured={featured}
          jobs={jobs}
          appHref={href.app}
          onOpen={(a) => open(a.name)}
          onRequestInstall={setReview}
          initialFilters={new URLSearchParams(window.location.search).get('q') ? { q: new URLSearchParams(window.location.search).get('q')! } : undefined}
        />
      </>
    );
  }

  return (
    <div className="d-stack">
      {body}
      {demoJob && (
        <div className="d-banner om-tone-agent" role="note">
          <span>
            Demo: <strong>{demoJob.app_name}</strong> is waiting for approval.
          </span>
          <Button size="sm" onClick={() => simulate(demoJob.action_id)}>
            Simulate approval
          </Button>
          <Button size="sm" variant="ghost" onClick={() => simulate(demoJob.action_id, false)}>
            Simulate a failed health check
          </Button>
        </div>
      )}
      {review && (
        <InstallReview
          key={review.id}
          app={review}
          plan={planFor(review.id)}
          open
          now={NOW}
          onClose={() => setReview(null)}
          onSubmit={(r) => {
            request(r);
            window.location.hash = href.app(review.id);
            window.scrollTo(0, 0);
          }}
        />
      )}
      <JobsTray jobs={jobs} now={NOW} onDismiss={(id) => setJobs((j) => j.filter((x) => x.action_id !== id))} />
    </div>
  );
}
