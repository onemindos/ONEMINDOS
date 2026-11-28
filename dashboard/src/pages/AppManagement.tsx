// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { useNavigate } from 'react-router';
import { Button, PageHeader } from '@onemind/ui';
import { openUrl } from '../data/adapters';
import { openAppOrSay } from '../lib/openApp';
import { useHub } from '../data/hub';
import { useSignedIn } from '../session';
import { usePoll } from '../lib/hooks';
import { useShell } from '../shell/Shell';
import { href } from '../shell/routes';
import { appPageHref } from '../lib/appPage';
import type { AppSettings } from '../api/types';
import { AppDepth } from './AppDepth';

export function AppManagement({ appId }: { appId: string }) {
  const hub = useHub();
  const { api } = useSignedIn();
  const shell = useShell();
  const navigate = useNavigate();
  const app = hub.apps.data?.find((a) => a.id === appId);
  const [changed, setChanged] = useState<NonNullable<AppSettings['values']>>({});
  const [invalid, setInvalid] = useState<string>();
  const settings = usePoll(async () => {
    if (!api.appSettings) throw new Error('Settings cannot be read by this gateway client.');
    return api.appSettings(appId);
  }, 0);
  const logs = usePoll(async () => {
    if (!api.appLogs) throw new Error('Logs cannot be read by this gateway client.');
    return api.appLogs(appId);
  }, 0);
  const job = hub.actionList.find((a) => a.params.app_id === appId);
  const busy = hub.actionList.some((a) => a.params.app_id === appId && ['requested', 'awaiting_approval', 'accepted', 'dispatched'].includes(a.state));
  const disabled = busy || hub.canRequest === 'no' || !!hub.apps.error || hub.freshness !== 'live';
  if (!app) return <p role="status">{hub.apps.error?.message ?? (hub.apps.loading ? 'Loading app…' : 'App not found.')}</p>;
  const present = app.installed || ['stopped', 'failed', 'unknown', 'starting', 'stopping', 'restarting', 'updating', 'configuring'].includes(app.status);
  return <>
    <a href={href.installed}>Installed apps</a> · <a href={appPageHref(appId)}>Health, usage, alerts and access</a>
    <PageHeader title={app.name || app.id} lede={`Gateway status: ${app.status}. Every change waits for owner approval.`} />
    <div role="group" aria-label={`${app.name || app.id} actions`}>
      {app.browser
        ? <Button disabled={!app.installed} onClick={() => navigate(href.browser(app.id))}>Open in a window</Button>
        : <Button disabled={!openUrl(app)} onClick={() => { const url = openUrl(app); if (url) openAppOrSay(api, app.name || app.id, url); }}>Open</Button>}
      <Button disabled={disabled || !present || app.status === 'stopped'} onClick={() => void shell.requestApp('app.restart', appId)}>Restart</Button>
      <Button disabled={disabled || !present} onClick={() => void shell.requestApp(app.status === 'stopped' ? 'app.start' : 'app.stop', appId)}>{app.status === 'stopped' ? 'Start' : 'Stop'}</Button>
      <Button disabled={disabled || !present || app.status === 'stopped'} onClick={() => void shell.requestApp('app.update', appId)}>Review update</Button>
      <Button disabled={disabled || !present} onClick={() => void shell.requestApp('app.remove', appId)}>Remove…</Button>
    </div>
    <p className="om-hint">Open goes through the OneMind sign-in: it opens the app at its own name on this box, and only people who may use the app get in. Removal keeps app data; deleting data is a separate operation.</p>
    {job && <p role="status">{job.type}: {job.state.replace(/_/g, ' ')}{job.progress ? ` — ${job.progress.step} (${job.progress.pct}%)` : ''}{job.result?.message ? ` — ${job.result.message}` : ''}</p>}
    {busy && <p role="status">A request for this app is in progress.</p>}
    <section aria-label="App settings">
      <h2>Settings</h2>
      {settings.error ? <p role="alert">{settings.error.message}</p> : settings.loading ? <p role="status">Loading settings…</p> : !settings.data?.values ? <p>Settings are not visible to this account.</p> : <form noValidate onSubmit={(e) => { e.preventDefault(); const bad = Array.from(e.currentTarget.elements).find((el) => el instanceof HTMLInputElement && !el.checkValidity()) as HTMLInputElement | undefined; setInvalid(bad ? `${bad.labels?.[0]?.textContent || bad.name}: ${bad.validationMessage || 'not allowed by this app'}` : undefined); if (!bad) void shell.requestApp('app.configure', appId, { settings: changed }); }}>
        {settings.data.fields.map((f) => {
          const value = changed[f.name] ?? settings.data!.values?.[f.name] ?? f.default ?? '';
          return <p key={f.name}><label>{f.title || f.name}{f.type === 'boolean' ? <input type="checkbox" checked={Boolean(value)} onChange={(e) => setChanged({ ...changed, [f.name]: e.target.checked })} /> : f.enum ? <select value={String(value)} onChange={(e) => setChanged({ ...changed, [f.name]: f.enum!.find((v) => String(v) === e.target.value) ?? e.target.value })}>{f.enum.map((v) => <option key={String(v)} value={String(v)}>{String(v)}</option>)}</select> : <input name={f.name} type={['number', 'integer'].includes(f.type) ? 'number' : 'text'} step={f.type === 'integer' ? 1 : 'any'} min={f.minimum} max={f.maximum} minLength={f.minLength} maxLength={f.maxLength} pattern={f.pattern} value={String(value)} onChange={(e) => setChanged({ ...changed, [f.name]: ['number', 'integer'].includes(f.type) ? Number(e.target.value) : e.target.value })} />}</label>{f.description && <small>{f.description}</small>}{f.restart !== false && changed[f.name] !== undefined && <small> Changing this restarts the app.</small>}</p>;
        })}
        {invalid && <p role="alert">{invalid}</p>}
        {settings.data.fields.length ? <><p>Settings are not secret. Never enter passwords, tokens or keys here.</p><Button type="submit" disabled={disabled || !Object.keys(changed).length}>Review settings</Button></> : <p>This app declares no configurable settings.</p>}
      </form>}
      <Button onClick={() => void settings.reload()}>Reload settings</Button>
    </section>
    <AppDepth appId={appId} />
    <section aria-label="App logs">
      <h2>Logs</h2>
      {logs.error ? <p role="alert">{logs.error.message}</p> : logs.loading ? <p role="status">Loading logs…</p> : <pre>{logs.data || 'The gateway returned no log lines.'}</pre>}
      <Button onClick={() => void logs.reload()}>Refresh logs</Button>
    </section>
    <a href={href.app(appId)}>Market page, trust and licence</a>
  </>;
}
