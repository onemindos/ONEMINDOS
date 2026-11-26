// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions > Modes (design §3.5, §3.5.1): how each agent's and person's requests are
// handled. GET /v1/permission-modes, GET /v1/agents, GET /v1/users; PUT /v1/permission-modes[/{principal}].
//
// Who may change a mode is the gateway's call, never this page's: tightening (toward Locked) needs no
// passkey; loosening is the owner's, with a fresh passkey, and never before the owner has one (F-8).
// The owner's own requests run directly and have no mode. Every new agent and person starts on
// Always ask (F-7).
import { useState } from 'react';
import { Link } from 'react-router';
import { Button, Card, Dialog, StatusPill } from '@onemind/ui';
import type { components as api } from '@onemind/sdk';
import { usePoll } from '../../lib/hooks';
import { MODE_TEXT, MODES, agentKey, explain, modeLabel, read, usePermSdk, useStepUp, type Mode } from '../../lib/permissions';
import { Load } from '../parts';

type PermissionMode = api['schemas']['PermissionMode'];
type AgentView = api['schemas']['AgentView'];
type Person = { id: string; display_name?: string; username?: string; role?: string; disabled?: boolean };
interface Row { key: string; name: string; kind: string; mode?: PermissionMode; owner?: boolean }

const ORDER = ['locked', 'ask', 'remember', 'auto', 'headless', 'bypass'];
const loosens = (from: string, to: string) => ORDER.indexOf(to) > ORDER.indexOf(from);

async function optional<T>(job: Promise<T>): Promise<T | null> {
  try {
    return await job;
  } catch {
    return null; // not this person's to list (403): the gateway still shows them the modes they may read
  }
}

export function Modes() {
  const sdk = usePermSdk();
  const stepUp = useStepUp();
  const data = usePoll(async () => {
    const [modes, agents, people] = await Promise.all([
      read(sdk.call<PermissionMode[]>({ method: 'GET', path: '/v1/permission-modes' })),
      optional(sdk.call<AgentView[]>({ method: 'GET', path: '/v1/agents' })),
      optional(sdk.call<Person[]>({ method: 'GET', path: '/v1/users' })),
    ]);
    return { modes, agents, people };
  }, 0);
  const [change, setChange] = useState<{ row: Row; to: Mode; reason: string; busy?: boolean; error?: string }>();
  const [done, setDone] = useState<string>();

  const save = async () => {
    if (!change) return;
    setChange({ ...change, busy: true, error: undefined });
    const path = change.row.key === '*' ? '/v1/permission-modes' : `/v1/permission-modes/${encodeURIComponent(change.row.key)}`;
    try {
      await stepUp((client) => client.call<PermissionMode>({ method: 'PUT', path, body: { mode: change.to, ...(change.reason.trim() ? { reason: change.reason.trim() } : {}) } }), sdk);
      setDone(`${change.row.name} is now on ${modeLabel(change.to)}.`);
      setChange(undefined);
      await data.reload();
    } catch (e) {
      setChange({ ...change, busy: false, error: explain(e) });
    }
  };

  return (
    <Load res={data} what="Loading permission modes">
      {({ modes, agents, people }) => {
        const household = modes.find((m) => m.principal === '*');
        const own = new Map(modes.filter((m) => m.principal !== '*').map((m) => [m.principal, m]));
        const rows: Row[] = [];
        const seen = new Set<string>();
        for (const a of agents ?? []) {
          const key = agentKey(a.id);
          seen.add(key);
          rows.push({ key, name: a.id.replace(/^agent:/, ''), kind: 'Agent', mode: own.get(key) });
        }
        for (const p of (people ?? []).filter((u) => !u.disabled)) {
          const key = `person:${p.id}`;
          seen.add(key);
          rows.push({ key, name: p.display_name || p.username || p.id, kind: 'Person', mode: own.get(key), owner: p.role === 'owner' });
        }
        for (const m of own.values()) if (!seen.has(m.principal)) rows.push({ key: m.principal, name: m.principal.replace(/^[a-z]+:/, ''), kind: m.principal.split(':')[0]!.replace(/^./, (c) => c.toUpperCase()), mode: m });
        const fallback = household?.mode ?? 'ask';
        const noPasskey = household?.owner_passkey === false;
        return (
          <>
            {done && <p className="om-note om-tone-ok" role="status">{done}</p>}
            {noPasskey && (
              <p className="om-note om-tone-warn" role="status">
                No owner passkey yet, so every requester is treated as Always ask and nothing can be loosened. <Link to="/settings/account">Add a passkey</Link>
              </p>
            )}
            <Card title="How requests are handled" subtitle="Moving toward Locked needs no passkey. Loosening is for the owner and asks for your passkey. The owner’s own requests run directly.">
              <ul className="dash-list" aria-label="Permission modes">
                {household && <ModeRow row={{ key: '*', name: 'Household default', kind: 'Everyone without their own mode' }} current={household.mode} onPick={(to) => setChange({ row: { key: '*', name: 'The household default', kind: '' }, to, reason: '' })} />}
                {rows.map((r) => (
                  <ModeRow key={r.key} row={r} current={r.mode?.mode ?? fallback} followsDefault={!r.owner && !r.mode?.own} onPick={(to) => setChange({ row: r, to, reason: '' })} />
                ))}
              </ul>
              {rows.length === 0 && <p className="om-hint">No agents or people have a mode of their own yet. They all follow the household default.</p>}
            </Card>
            {change && (
              <Dialog
                open
                role="alertdialog"
                title={`Change ${change.row.name} to ${modeLabel(change.to)}?`}
                description={MODE_TEXT[change.to]?.help}
                onClose={() => (change.busy ? undefined : setChange(undefined))}
                actions={<>
                  <Button onClick={() => setChange(undefined)} disabled={change.busy}>Cancel</Button>
                  <Button variant="primary" busy={change.busy} onClick={() => void save()}>{loosens(currentOf(change.row, household), change.to) ? 'Confirm with passkey' : 'Change mode'}</Button>
                </>}
              >
                {loosens(currentOf(change.row, household), change.to) && <p>This lets {change.row.name} do more without asking you. Your passkey confirms it.</p>}
                <label>Why (optional, kept in the activity log)
                  <input value={change.reason} maxLength={200} onChange={(e) => setChange({ ...change, reason: e.target.value })} />
                </label>
                {change.error && <p className="om-note om-tone-bad" role="alert">{change.error}</p>}
              </Dialog>
            )}
          </>
        );
      }}
    </Load>
  );
}

function currentOf(row: Row, household?: PermissionMode): string {
  return row.key === '*' ? household?.mode ?? 'ask' : row.mode?.mode ?? household?.mode ?? 'ask';
}

function ModeRow({ row, current, followsDefault, onPick }: { row: Row; current: string; followsDefault?: boolean; onPick: (to: Mode) => void }) {
  const id = `mode-${row.key.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
  return (
    <li className="dash-actions">
      <span>
        <strong>{row.name}</strong> <span className="om-hint">{row.kind}{followsDefault ? ' · follows the household default' : ''}</span>
      </span>
      {row.owner ? (
        <StatusPill tone="info" label="Owner: runs directly" />
      ) : (
        <>
          <label htmlFor={id} className="om-visually-hidden">Mode for {row.name}</label>
          <select id={id} value={current} onChange={(e) => onPick(e.target.value as Mode)}>
            {MODES.map((m) => <option key={m} value={m}>{MODE_TEXT[m]!.label}</option>)}
            {!MODES.includes(current as Mode) && <option value={current} disabled>{modeLabel(current)}</option>}
          </select>
        </>
      )}
    </li>
  );
}

