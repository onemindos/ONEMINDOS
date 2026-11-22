// SPDX-License-Identifier: Apache-2.0
// A browser app (Neko, #593) in a desktop window with the person's own profile (#692). The gateway
// starts this person's pod and answers the URL of their browser host (<app>--<key>.<box domain>),
// which its proxy serves to them only; the window frames that host. Close stops the pod and keeps the
// profile. Reset profile only files a request: an owner approves it in Approvals before anything is erased.
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router';
import { Button, Dialog, PageHeader, useToast } from '@onemind/ui';
import type { BrowserSession, OneMindApi } from '../api/client';
import { useHub, errorText } from '../data/hub';
import { useSignedIn } from '../session';
import { href } from './routes';

type Api = Pick<OneMindApi, 'openAppSession' | 'openBrowser' | 'closeBrowser' | 'resetBrowserProfile'>;

/** Sign this browser in for app hosts, then start the person's own browser pod. */
export async function startBrowser(api: Api, appId: string): Promise<BrowserSession> {
  if (!api.openBrowser) throw new Error('This gateway client cannot open browser windows.');
  await api.openAppSession?.();
  return api.openBrowser(appId);
}

export function BrowserWindowView({ appId, name, api, onClosed }: { appId: string; name: string; api: Api; onClosed: () => void }) {
  const toast = useToast();
  const [session, setSession] = useState<BrowserSession>();
  const [error, setError] = useState<string>();
  const [confirm, setConfirm] = useState(false);
  useEffect(() => {
    let live = true;
    startBrowser(api, appId).then((s) => live && setSession(s), (e: unknown) => live && setError(errorText(e).message));
    return () => { live = false; };
  }, [api, appId]);
  const close = async () => {
    try { await api.closeBrowser?.(appId); }
    catch (e) { toast.show({ tone: 'bad', title: `Could not stop ${name}`, body: errorText(e).message }); }
    onClosed();
  };
  const reset = async () => {
    setConfirm(false);
    try {
      if (!api.resetBrowserProfile) throw new Error('This gateway client cannot reset a browser profile.');
      await api.resetBrowserProfile(appId);
      toast.show({ tone: 'info', title: 'Reset requested', body: 'Your profile is erased only after an owner approves it in Approvals.' });
    } catch (e) {
      toast.show({ tone: 'bad', title: 'Could not request a reset', body: errorText(e).message });
    }
  };
  return <>
    <PageHeader title={name} lede="Your own profile, kept on the box. Nobody else can open this window." />
    <div role="group" aria-label={`${name} window`}>
      <Button onClick={() => void close()}>Close</Button>
      <Button disabled={!session} onClick={() => setConfirm(true)}>Reset profile…</Button>
    </div>
    {error && <p role="alert">{`OneMind could not open ${name}: ${error}`}</p>}
    {!error && !session && <p role="status">Starting {name}…</p>}
    {session && <iframe className="om-browser-frame" title={`${name}, your profile`} src={session.url} allow="clipboard-read; clipboard-write; fullscreen" referrerPolicy="no-referrer" />}
    {confirm && <Dialog open title="Reset your browser profile?" onClose={() => setConfirm(false)} actions={<><Button onClick={() => setConfirm(false)}>Cancel</Button><Button variant="primary" onClick={() => void reset()}>Ask the owner</Button></>}>
      <p>Bookmarks, logins and history in {name} are erased. This waits for an owner to approve it.</p>
    </Dialog>}
  </>;
}

/** The /browser/:appId window. */
export function BrowserWindow() {
  const { appId = '' } = useParams();
  const { api } = useSignedIn();
  const hub = useHub();
  const navigate = useNavigate();
  const app = hub.apps.data?.find((a) => a.id === appId);
  if (!app) return <p role="status">{hub.apps.error?.message ?? (hub.apps.loading ? 'Loading…' : 'App not found.')}</p>;
  if (!app.browser) return <p role="status">{`${app.name || app.id} is not a browser app.`} <a href={href.manage(app.id)}>Manage it</a></p>;
  return <BrowserWindowView key={appId} appId={appId} name={app.name || app.id} api={api} onClosed={() => navigate('/')} />;
}
