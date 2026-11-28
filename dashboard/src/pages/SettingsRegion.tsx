// SPDX-License-Identifier: Apache-2.0
// Settings > Language & region (P-11): the keyboard layout of the box's text console and its own screen.
// The change is a request: an owner approves it on the Approvals screen, then the box saves the layout on its data disk
// (it survives restarts and updates) and loads it. This page only asks; it never approves.
import { useMemo, useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Button, Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { href } from '../shell/routes';
import { usePoll } from '../lib/hooks';

type View = components['schemas']['KeyboardView'];
type Action = components['schemas']['Action'];

function useSdk() {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

function checked<T>(request: Promise<T>) {
  return request.catch((error: unknown) => {
    if (error instanceof OneMindError) throw new ApiError(error.status, error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown', error.message);
    throw error;
  });
}

const label = (layout: string, variant: string) => (variant ? `${layout} (${variant})` : layout);

export function SettingsRegion() {
  const api = useSdk();
  const { role } = useShell();
  // Only an owner may read it (403 for everyone else), so nobody else asks.
  const view = usePoll<View | undefined>(() => (role === 'owner' ? checked(api.call<View>({ method: 'GET', path: '/v1/system/keyboard' })) : Promise.resolve(undefined)), role === 'owner' ? 5000 : 0);
  const [layout, setLayout] = useState<string>();
  const [variant, setVariant] = useState('');
  const [asking, setAsking] = useState(false);
  const [asked, setAsked] = useState<{ id: string; text: string }>();
  const [error, setError] = useState('');
  const v = view.data;
  const layouts = v?.layouts ?? [];
  const current = v?.current;
  const picked = layouts.find((l) => l.id === (layout ?? current?.layout));
  const names = (id: string, vr: string) => {
    const l = layouts.find((x) => x.id === id);
    return (vr && l?.variants.find((x) => x.id === vr)?.name) || l?.name || id;
  };
  const same = !!current && (layout ?? current.layout) === current.layout && variant === current.variant;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const chosen = layout ?? current?.layout;
    if (role !== 'owner' || !chosen || asking) return;
    setAsking(true);
    setError('');
    setAsked(undefined);
    try {
      const body = { layout: chosen, ...(variant ? { variant } : {}), reason: 'Asked in Settings > Language & region' };
      const action = await checked(api.call<Action>({ method: 'POST', path: '/v1/system/keyboard', body }));
      setAsked({ id: action.id, text: `Asked for ${names(chosen, variant)}.` });
    } catch (e) {
      setError(e instanceof ApiError && e.status === 404 ? 'This box does not offer that layout.' : e instanceof Error ? e.message : 'Could not ask for the change.');
    } finally {
      setAsking(false);
    }
  };
  let body;
  if (role !== 'owner') {
    body = <p className="om-hint">Only an owner can see or change the box&rsquo;s keyboard layout.</p>;
  } else if (view.error && !v) {
    body = <p role="alert">{view.error.status === 403 ? 'Owner only' : 'Could not read the keyboard layout from this box.'}</p>;
  } else if (!v) {
    body = <p className="om-hint">Loading&hellip;</p>;
  } else if (!v.available || !current) {
    body = <p role="alert">The keyboard layout cannot be read now: {v.message ?? 'the box did not answer'}.</p>;
  } else {
    body = (
      <>
        <dl>
          <dt>Keyboard layout</dt>
          <dd>
            {names(current.layout, current.variant)} <code>{label(current.layout, current.variant)}</code>
            {v.seeded ? ' (the default: nothing chosen yet)' : ''}
          </dd>
        </dl>
        <form onSubmit={(event) => void submit(event)}>
          <label htmlFor="kb-layout">Layout</label>{' '}
          <select id="kb-layout" value={layout ?? current.layout} onChange={(e) => { setLayout(e.target.value); setVariant(''); }}>
            {layouts.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>{' '}
          {picked && picked.variants.length > 0 && (
            <>
              <label htmlFor="kb-variant">Variant</label>{' '}
              <select id="kb-variant" value={variant} onChange={(e) => setVariant(e.target.value)}>
                <option value="">Standard</option>
                {picked.variants.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}
              </select>{' '}
            </>
          )}
          <Button type="submit" disabled={asking || same}>Ask to change keyboard</Button>
        </form>
        {asked && (
          <p role="status">
            {asked.text} Approve it on the <Link to={href.approval(asked.id)}>Approvals</Link> screen and the box switches.
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </>
    );
  }
  return (
    <>
      <PageHeader title="Language & region" lede="The keyboard of the box itself." />
      <Card title="Keyboard layout">
        <p className="om-hint">
          This is the keyboard the box uses for its text console (Ctrl+Alt+F2) and its own screen. It does not change the keyboard of the phone or computer you are using
          now. An owner approves the change; it is kept across restarts and updates.
        </p>
        {body}
      </Card>
    </>
  );
}
