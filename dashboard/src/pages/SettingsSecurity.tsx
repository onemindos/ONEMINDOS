// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError, type components } from '@onemind/sdk';
import { Card, PageHeader } from '@onemind/ui';
import { ApiError } from '../api/types';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { useShell } from '../shell/Shell';
import { AccessGrants } from './AccessGrants';
import { AgentInputsEditor, AppSharingEditor } from './PermissionEditors';

const account = '/settings/account';
const object = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
const count = (unit: string) => (value: unknown) => Array.isArray(value) ? `${value.length} ${unit}` : undefined;

async function get(sdk: OneMind, path: string) {
  return sdk.call<unknown>({ method: 'GET', path });
}

async function summarize<T>(job: Promise<T>, label: (value: T) => string | undefined = (value) => typeof value === 'string' ? value : undefined) {
  try {
    return label(await job) ?? 'Unknown';
  } catch (error) {
    return error instanceof OneMindError && error.status === 403 ? 'Owner only' : 'Unknown';
  }
}

async function exposure(sdk: OneMind) {
  const installed = (await sdk.apps.list()).filter((app) => app.installed);
  const modes = await Promise.all(installed.map((app) => get(sdk, `/v1/apps/${encodeURIComponent(app.id)}/exposure`)));
  const tiers = modes.map((value) => object(value).tier);
  return tiers.every((tier) => tier === 'private' || tier === 'mesh' || tier === 'public')
    ? `${tiers.filter((tier) => tier !== 'private').length} externally reachable` : undefined;
}

export function SettingsSecurity() {
  const { role } = useShell();
  const sdk = useSecuritySdk();
  const owner = role === 'owner';
  const response = usePoll(async () => {
    const own = [
      ['Sign-in keys', '/settings/sign-in-keys', summarize(get(sdk, '/v1/auth/passkeys'), (data) => {
        if (!Array.isArray(data)) return undefined;
        const proven = data.filter((item) => ['L2', 'L3'].includes(String(object(item).level))).length;
        return `${data.length} registered · ${proven} proven`;
      })],
      // GET /v1/auth/methods; "Off" is not a warning: passkeys come first and the code is a fallback (D-030).
      ['Authenticator code', account, summarize(get(sdk, '/v1/auth/methods'), (data) => {
        const totp = object(data).totp;
        return totp === true ? 'On' : totp === false ? 'Off (a fallback; passkeys come first)' : undefined;
      })],
      ['Signed-in devices', account, summarize(get(sdk, '/v1/auth/sessions'), count('sessions'))],
      ['API tokens', account, summarize(get(sdk, '/v1/tokens'), (data) => {
        if (!Array.isArray(data)) return undefined;
        const expiry = data.map((item) => object(item).expires_at)
          .filter((value): value is string => typeof value === 'string' && Number.isFinite(Date.parse(value))).sort();
        return expiry[0] ? `${data.length} issued · first expiry ${new Date(expiry[0]).toLocaleDateString()}` : `${data.length} issued`;
      })],
    ] as const;
    const box = owner ? [
      ['Agents', '/agents', summarize(get(sdk, '/v1/agents'), count('registered'))],
      ['Agent kill switch', '/agents', summarize(get(sdk, '/v1/agents/kill-switch'), (data) => {
        const value = object(data).on;
        return value === true ? 'On' : value === false ? 'Off' : undefined;
      })],
      ['Audit chain', '/activity', summarize(get(sdk, '/v1/audit/verify'), (data) => {
        const value = object(data).ok;
        return value === true ? 'Verified' : value === false ? 'Verification failed' : undefined;
      })],
      ['Certificate', '/settings/network', summarize(get(sdk, '/v1/tls'), (data) => {
        const value = object(data);
        if (value.https === false) return 'HTTPS off';
        return typeof value.not_after === 'string' && Number.isFinite(Date.parse(value.not_after))
          ? `Expires ${new Date(value.not_after).toLocaleDateString()}` : undefined;
      })],
      ['Verification levels', '/settings/verification', summarize(get(sdk, '/v1/verification-requirements'), (data) => {
        const t = object(data);
        if (t.recovery_needed === true) return 'Waiting for a proven key';
        if (t.grace === true) return 'Before your first proven key: confirmed at the box';
        return typeof t.household_level === 'string' ? `Strongest key ${t.household_level}` : t.household_level === null ? 'No passkey yet' : undefined;
      })],
      ['Standing approvals', '/settings/automation', summarize(get(sdk, '/v1/approval-policies'), count('configured'))],
      ['Physical lockout', '/settings/automation', summarize(get(sdk, '/v1/physical/lockout'), (data) => {
        const value = object(data).locked;
        return value === true ? 'Locked' : value === false ? 'Unlocked' : undefined;
      })],
      ['App exposure', '/installed', summarize(exposure(sdk))],
    ] as const : [];
    return Promise.all([...own, ...box].map(async ([title, href, status]) => ({ title, href, state: await status })));
  }, 0);
  return <>
    <PageHeader title="Security overview" />
    <Card title="Security status">
      {response.data ? <dl>{response.data.map(({ title, href, state }) => <div key={title}>
        <dt><Link to={href}>{title}</Link></dt><dd>{state}</dd>
      </div>)}</dl> : <p role="status">Checking security settings…</p>}
    </Card>
  </>;
}

const names = (value: unknown) => Array.isArray(value) && value.every((item) => typeof item === 'string') ? value.join(', ') || 'None' : 'Unknown';

function useSecuritySdk() {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

type By = 'person' | 'app' | 'agent';
const groups: Record<By, string> = { person: 'By person', app: 'By app', agent: 'By agent' };

function PermissionList({ sdk, by }: { sdk: OneMind; by: By }) {
  const [selected, setSelected] = useState('');
  const owner = useShell().role === 'owner';
  const list = usePoll(async () => {
    const path = by === 'person' ? '/v1/users' : by === 'app' ? '/v1/apps' : '/v1/agents';
    try {
      const value = await get(sdk, path);
      if (!Array.isArray(value)) return { status: 'Unknown', rows: [] };
      const rows = value.flatMap((item) => {
        const record = object(item);
        if (typeof record.id !== 'string') return [];
        const label = record.display_name ?? record.name;
        return [{ id: record.id, name: typeof label === 'string' ? label : record.id, role: record.role }];
      });
      return { status: rows.length ? '' : 'None', rows };
    } catch (error) {
      return { status: error instanceof OneMindError && error.status === 403 ? 'Owner only' : 'Unknown', rows: [] };
    }
  }, 0);
  const current = list.data?.rows.find((item) => item.id === selected);
  return <>
    {!list.data ? <p>Checking permissions…</p> : list.data.status ? <p>{list.data.status}</p> :
      <label>{by === 'person' ? 'Person' : by === 'app' ? 'App' : 'Agent'}{' '}
        <select value={selected} onChange={(event) => setSelected(event.target.value)}>
          <option value="">Select</option>
          {list.data.rows.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select>
      </label>}
    {current && <PermissionDetail key={current.id} sdk={sdk} by={by} id={current.id} role={current.role} />}
    {/* Owner writer screens (#1214): the hub asks for the step-up in place when a change adds power. */}
    {current && owner && by === 'app' && <AppSharingEditor key={`share-${current.id}`} appId={current.id} appName={current.name} />}
    {current && owner && by === 'agent' && <AgentInputsEditor key={`inputs-${current.id}`} agentId={current.id} />}
  </>;
}

function PermissionDetail({ sdk, by, id, role }: { sdk: OneMind; by: By; id: string; role: unknown }) {
  const chosen = encodeURIComponent(id);
  const result = usePoll(async () => {
    if (by === 'app') return [await summarize(get(sdk, `/v1/apps/${chosen}/access`), (data) => {
      const access = object(data);
      const people = Array.isArray(access.people) ? access.people.map((person) => object(person).display_name) : undefined;
      return `Roles: ${names(access.roles)}. People: ${names(people)}.`;
    })];
    if (by === 'person') return Promise.all([
      summarize(get(sdk, `/v1/family/profiles/${chosen}`), (data) => {
        const policy = object(data);
        if (!('allowed_apps' in policy)) return undefined;
        const apps = policy.allowed_apps === null ? 'Inherited' : names(policy.allowed_apps);
        const rating = typeof policy.max_age_rating === 'number' ? String(policy.max_age_rating) : 'Not set';
        return `Allowed apps: ${apps}. Maximum age rating: ${rating}.`;
      }),
      summarize(get(sdk, '/v1/files/grants'), (data) => Array.isArray(data)
        ? `${data.length} visible file grants across the box` : undefined),
    ]);
    return [await summarize(get(sdk, '/v1/tokens'), (data) => {
      if (!Array.isArray(data)) return undefined;
      const scopes = data.map(object).filter((token) => token.kind === 'agent' && token.principal_id === id)
        .flatMap((token) => Array.isArray(token.scopes) ? token.scopes : []);
      return scopes.length ? `Token scopes: ${names([...new Set(scopes)])}` : 'No token scopes reported';
    })];
  }, 0);
  return <>
    {typeof role === 'string' && <p>Role {role}</p>}
    {result.data?.map((item, index) => <p key={index}>{item}</p>)}
  </>;
}

export function SettingsPermissions() {
  const sdk = useSecuritySdk();
  const [by, select] = useState<By>('person');
  return <>
    <PageHeader title="Permissions" />
    <Card title="Who has access" subtitle="Pick a person, an app or an agent. Owners can change who opens an app and what an agent reads.">
      <div role="group" aria-label="View permissions">
        {(Object.keys(groups) as By[]).map((group) => <button type="button" key={group} aria-pressed={by === group} onClick={() => select(group)}>{groups[group]}</button>)}
      </div>
      <PermissionList key={by} sdk={sdk} by={by} />
    </Card>
    <AccessGrants />
  </>;
}

function measured<T>(request: Promise<T>) {
  return request.catch((error: unknown) => {
    if (error instanceof OneMindError) throw new ApiError(error.status, error.status === 401 ? 'unauthenticated' : error.status === 403 ? 'permission_denied' : 'unknown', error.message);
    throw error;
  });
}

type RuntimeRow = { id: string; name: string; cpu: number | null; memory: number | null; stale: boolean };

export function SettingsActivityMonitor() {
  const sdk = useSecuritySdk();
  const [sort, setSort] = useState<'name' | 'cpu' | 'memory'>('name');
  const usage = usePoll(() => measured(sdk.call<components['schemas']['Usage']>({ method: 'GET', path: '/v1/usage' })), 5000);
  const services = usePoll(() => measured(sdk.call<components['schemas']['ServicesView']>({ method: 'GET', path: '/v1/system/services' })), 5000);
  const activity = usePoll(async () => Promise.all([
    summarize(get(sdk, '/v1/agents'), count('registered agents')),
    summarize(sdk.actions.list(), (data) => {
      const pending = data.filter((action) => action.requested_by.kind === 'agent' && action.state === 'awaiting_approval');
      return `${pending.length} agent requests waiting for approval`;
    }),
    summarize(get(sdk, '/v1/auth/sessions'), count('sessions')),
  ]), 5000);
  const rows: RuntimeRow[] = [
    ...(usage.error?.status === 403 ? [] : usage.data?.apps.items ?? []).map((app) => ({
      id: `app-${app.app_id}`, name: app.name ?? app.app_id, cpu: app.cpu_millicores ?? null, memory: app.mem_mib ?? null,
      stale: !!usage.data?.apps.stale || !!usage.error,
    })),
    ...(services.error?.status === 403 ? [] : services.data?.services ?? []).filter((service) => service.installed && service.active_state === 'active').map((service) => ({
      id: service.unit, name: service.name, cpu: null, memory: service.memory_bytes == null ? null : service.memory_bytes / 2 ** 20,
      stale: !!services.error,
    })),
  ];
  rows.sort((a, b) => sort === 'name' ? a.name.localeCompare(b.name) : (b[sort] ?? -1) - (a[sort] ?? -1) || a.name.localeCompare(b.name));
  return <>
    <PageHeader title="Activity monitor" />
    <Card title="Apps and system services">
      {(usage.error || services.error) && <p role="status">Some current metrics are unknown. Older figures are marked stale.</p>}
      <table><thead><tr>
        <th scope="col" aria-sort={sort === 'name' ? 'ascending' : 'none'}><button type="button" onClick={() => setSort('name')}>Name</button></th>
        <th scope="col" aria-sort={sort === 'cpu' ? 'descending' : 'none'}><button type="button" onClick={() => setSort('cpu')}>CPU (mCPU)</button></th>
        <th scope="col" aria-sort={sort === 'memory' ? 'descending' : 'none'}><button type="button" onClick={() => setSort('memory')}>Memory (MiB)</button></th>
      </tr></thead><tbody>{rows.map((item) => <tr key={item.id} className={item.stale ? 'om-hint' : undefined}>
        <th scope="row">{item.name}{item.stale && ' · Stale'}</th><td>{item.cpu ?? 'Unknown'}</td><td>{item.memory?.toFixed(1) ?? 'Unknown'}</td>
      </tr>)}</tbody></table>
      {!rows.length && <p>No measurements are available.</p>}
      <Link to="/usage">Usage history</Link>
    </Card>
    <Card title="Agents and sessions">
      <ul>{(activity.data ?? []).map((value, index) => <li key={index}>{value}</li>)}</ul>
      <div className="dash-actions"><Link to="/agents">Manage agents</Link><Link to="/activity">Audit activity</Link></div>
    </Card>
  </>;
}
