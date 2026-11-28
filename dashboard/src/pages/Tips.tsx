// SPDX-License-Identifier: Apache-2.0
import { useMemo, useRef, useState } from 'react';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { Link, matchPath, useLocation, useParams } from 'react-router';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { SCREENS } from '../screens/registry';
import { useSignedIn } from '../session';
import { useKeymap } from '../shell/keys/useKeymap';
import { Load } from './parts';
import { TipSetupStatus } from './TipSetupStatus';

type Tip = components['schemas']['TipView'];

const tipsPath = '/tips';
const tipPath = (id: string) => `${tipsPath}/${encodeURIComponent(id)}`;

async function fromHub<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (error) {
    if (error instanceof OneMindError) {
      const code = error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown';
      throw new ApiError(error.status, code, error.message, error.reason);
    }
    throw error;
  }
}

function useTipPack(client: OneMind) {
  return usePoll(async () => {
    const [list, collections] = await fromHub(Promise.all([client.tips.list(), client.tips.collections()]));
    return { ...list, ...collections };
  }, 0);
}

function CopyLink() {
  const { pathname, search, hash } = useLocation();
  const [status, setStatus] = useState('');

  const copy = async () => {
    const url = new URL(window.location.origin);
    url.pathname = pathname;
    url.search = search;
    url.hash = hash;
    try {
      await navigator.clipboard.writeText(url.href);
      setStatus('Link copied.');
    } catch {
      setStatus('Could not copy the link.');
    }
  };

  return <div>
    <Button onClick={() => void copy()}>Copy link</Button>
    {status && <p role="status">{status}</p>}
  </div>;
}

function TipLinks({ tips }: { tips: readonly Tip[] }) {
  return <ul>{tips.map(tip => <li key={tip.id}>
    <Link to={tipPath(tip.id)}>{tip.title}</Link>
    {tip.state === 'done' && <span> · Done</span>}
  </li>)}</ul>;
}

function Checklist({ tips, ids }: { tips: readonly Tip[]; ids: readonly string[] }) {
  const byId = new Map(tips.map(tip => [tip.id, tip]));
  const steps = ids.flatMap(id => {
    const tip = byId.get(id);
    return tip ? [tip] : [];
  });
  return steps.length ? <TipLinks tips={steps} /> : <p>No checklist steps are available for this account.</p>;
}

export function TipsGuide({ client }: { client: OneMind }) {
  const res = useTipPack(client);
  return <Card title="Getting started guide">
    {res.error?.status === 403
      ? <p role="status">Your account cannot view the getting started guide.</p>
      : <Load res={res} what="Loading the guide">{data => data.pack
        ? <><Checklist tips={data.tips} ids={data.checklist} /><TipSetupStatus client={client} /></>
        : <p>This hub has no Tips pack for its current version.</p>}</Load>}
    <Link to={tipsPath}>Browse all Tips</Link>
  </Card>;
}

/** What changed in the running version (GET /v1/tips/whats-new), newest first as the pack lists it. */
function WhatsNew({ client }: { client: OneMind }) {
  const res = usePoll(() => fromHub(client.tips.whatsNew()), 0);
  return <Card title="What’s new">
    <Load res={res} what="Loading what’s new">{data => <>
      <p>You are running OneMind {data.os_version}.</p>
      {data.entries.length
        ? <ul>{data.entries.map(entry => <li key={`${entry.version}-${entry.title}`}>
          <strong>{entry.title}</strong> <span className="om-hint">({entry.version})</span>
          <p>{entry.body}</p>
        </li>)}</ul>
        : <p>Nothing new is listed for this version.</p>}
    </>}</Load>
  </Card>;
}

function TipsIndex({ client }: { client: OneMind }) {
  const res = useTipPack(client);
  const [query, setQuery] = useState('');
  const [collection, setCollection] = useState('');
  const searchRef = useRef<HTMLInputElement>(null);
  useKeymap({
    'tips-search': () => {
      const input = searchRef.current;
      if (!input || input.closest('[hidden], [inert]')) return false;
      input.focus();
    },
  });

  return <div className="dash-stack">
    <PageHeader title="Tips" actions={<CopyLink />} />
    <Load res={res} what="Loading Tips">{data => {
      if (!data.pack) return <p>This hub has no Tips pack for its current version.</p>;
      const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
      const tips = data.tips.filter(tip => {
        if (collection && tip.collection !== collection) return false;
        const text = `${tip.title}\n${tip.body}`.toLowerCase();
        return words.every(word => text.includes(word));
      });
      return <>
        <WhatsNew client={client} />
        <Card title="Getting started checklist">
          <Checklist tips={data.tips} ids={data.checklist} />
          <TipSetupStatus client={client} />
        </Card>
        <Card title="Collections">
          <div className="dash-actions">
            <label>Search Tips <input ref={searchRef} type="search" value={query} onChange={event => setQuery(event.target.value)} /></label>
            <label>Collection <select value={collection} onChange={event => setCollection(event.target.value)}>
              <option value="">All collections</option>
              {data.collections.map(item => <option key={item.id} value={item.id}>{item.title} ({item.count})</option>)}
            </select></label>
          </div>
          {tips.length ? <TipLinks tips={tips} /> : <p role="status">No tips match your search.</p>}
        </Card>
      </>;
    }}</Load>
  </div>;
}

function dashboardTarget(path: string) {
  if (!path.startsWith('/') || path.startsWith('//') || /[\\\s]/.test(path)) return undefined;
  const { pathname, search, hash } = new URL(path, window.location.origin);
  const routable = SCREENS.some(screen =>
    [screen.path, ...(screen.extra ?? []).map(route => route.path), ...(screen.redirects ?? []).map(route => route.from)]
      .some(pattern => matchPath(pattern, pathname)));
  return routable ? { pathname, search, hash } : undefined;
}

function TipDetail({ client, id }: { client: OneMind; id: string }) {
  const res = usePoll(() => fromHub(client.tips.get(id)), 0);
  return <div className="dash-stack">
    <Link to={tipsPath}>All Tips</Link>
    <PageHeader title={res.data?.title ?? 'Tip'} actions={<CopyLink />} />
    <Load res={res} what="Loading the tip">{tip => {
      const target = dashboardTarget(tip.opens.dashboard);
      return <Card>
        {tip.body.split(/\n\s*\n/).map((paragraph, index) => <p key={index}>{paragraph}</p>)}
        {tip.clip && <div>
          <h2>Clip</h2>
          <p>{tip.clip.caption}</p>
          <p>This hub does not serve the video.</p>
        </div>}
        {target
          ? <Link className="om-btn om-btn-primary" to={target}>Open</Link>
          : <p>The screen for this tip is unavailable.</p>}
      </Card>;
    }}</Load>
  </div>;
}

function LiveTips({ token }: { token: string }) {
  const client = useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
  const { tipId } = useParams();
  return tipId ? <TipDetail key={tipId} client={client} id={tipId} /> : <TipsIndex client={client} />;
}

export function Tips() {
  const { token, person, mock } = useSignedIn();
  return mock
    ? <><PageHeader title="Tips" actions={<CopyLink />} /><p>Connect to a hub to see its Tips pack.</p></>
    : <LiveTips key={person} token={token} />;
}
