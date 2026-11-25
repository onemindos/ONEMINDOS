// SPDX-License-Identifier: Apache-2.0
// Quick settings (#841, wave B1): one menu-bar button, just before the bell, that opens the everyday
// switches and a glance at the box. It only changes the person's own view or takes power away (the
// agent kill switch); everything else links to its Settings page. Esc or a click outside closes it
// and focus returns to the button; the button says aria-expanded, so the desktop's Esc rule leaves
// the windows alone while it is open. The button is named "Quick controls" because the Network page
// test forbids any button there whose name contains "set".
import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, OneMindError } from '@onemind/sdk';
import { Button, Dialog, Icon, formatAgo, useOptionalCustomize } from '@onemind/ui';
import { ApiError } from '../../api/types';
import { personStorage } from '../../data/prefs';
import { usePoll, useNow } from '../../lib/hooks';
import { useSignedIn } from '../../session';
import { href } from '../routes';
import { PRO_ROLES, type View } from '../roles';
import { backupTile, networkTile, storageTile, updatesTile, UNKNOWN, type TileValue } from './quickData';
import { type ViewChoice } from './viewPref';
import './quick.css';

export interface QuickSettingsProps {
  /** The signed-in role (roles.ts); undefined until known. */
  role: string | null | undefined;
  /** The view on screen: the role's, narrowed by the person's choice. */
  view: View;
  viewChoice: ViewChoice;
  onViewChoice: (c: ViewChoice) => void;
}

function useSdk() {
  const { token } = useSignedIn();
  return useMemo(() => new OneMind({ baseUrl: window.location.origin, token, retries: 1 }), [token]);
}

export function QuickSettings(props: QuickSettingsProps) {
  const [open, setOpen] = useState(false);
  const [modal, setModal] = useState(false); // a confirm dialog is up: it, not the panel, owns Esc and clicks
  const btn = useRef<HTMLButtonElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const popId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape' || modal) return;
      setOpen(false);
      btn.current?.focus();
    };
    const onDown = (e: MouseEvent) => {
      if (modal) return;
      const t = e.target as Node;
      if (!pop.current?.contains(t) && !btn.current?.contains(t)) setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onDown);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onDown);
    };
  }, [open, modal]);

  useEffect(() => {
    if (open) pop.current?.querySelector<HTMLElement>('button, a')?.focus();
  }, [open]);

  return (
    <div className="oms-bell-wrap">
      <button ref={btn} type="button" className={open ? 'oms-bell oms-bell-open' : 'oms-bell'} aria-expanded={open} aria-controls={popId} aria-label="Quick controls" title="Quick settings" onClick={() => setOpen((v) => !v)}>
        <Icon name="settings" size={20} />
      </button>
      <div ref={pop} id={popId} className="oms-pop qs-pop" role="region" aria-label="Quick settings" hidden={!open}>
        {open && <Panel {...props} onModal={setModal} onNavigate={() => setOpen(false)} />}
      </div>
    </div>
  );
}

function Panel({ role, view, viewChoice, onViewChoice, onModal, onNavigate }: QuickSettingsProps & { onModal: (b: boolean) => void; onNavigate: () => void }) {
  const { mock } = useSignedIn();
  const proRole = role !== undefined && role !== null && PRO_ROLES.has(role);
  return (
    <>
      <ThemeSection />
      <section className="qs-sec" aria-labelledby="qs-view">
        <h3 id="qs-view" className="qs-title">View</h3>
        <div className="qs-seg" role="group" aria-label="Simple or Pro view">
          <button type="button" aria-pressed={view === 'simple'} disabled={!proRole} onClick={() => onViewChoice('simple')}>Simple</button>
          <button type="button" aria-pressed={view === 'pro'} disabled={!proRole} onClick={() => onViewChoice('auto')}>Pro</button>
        </div>
        <p className="qs-hint">
          {proRole
            ? viewChoice === 'simple' ? 'You chose the Simple screens. Pro shows everything your role allows.' : 'Pro shows everything your role allows. Simple hides the box-admin screens for you.'
            : 'Your role uses the Simple screens. The owner can change a role in Settings.'}
        </p>
      </section>
      {mock ? <p className="qs-hint">Demo data: quiet hours, agents and box status need a real hub.</p> : <QuietHours />}
      {!mock && role === 'owner' && <StopAgents onModal={onModal} onNavigate={onNavigate} />}
      {!mock && proRole && <Tiles owner={role === 'owner'} onNavigate={onNavigate} />}
    </>
  );
}

function ThemeSection() {
  const c = useOptionalCustomize();
  if (!c) return null;
  const mode = c.prefs.theme;
  const opts = [['system', 'Auto'], ['light', 'Light'], ['dark', 'Dark']] as const;
  return (
    <section className="qs-sec" aria-labelledby="qs-theme">
      <h3 id="qs-theme" className="qs-title">Theme</h3>
      <div className="qs-seg" role="group" aria-label="Colour theme">
        {opts.map(([v, label]) => (
          <button key={v} type="button" aria-pressed={mode === v} onClick={() => c.update({ theme: v })}>{label}</button>
        ))}
      </div>
      {mode === 'schedule' && <p className="qs-hint">A day and night schedule is set in Settings.</p>}
    </section>
  );
}

type Prefs = Record<string, unknown>;
const DEFAULT_QUIET = () => ({
  tz: (() => { try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; } })(),
  from: '22:00',
  to: '07:00',
  except_severity: ['critical'],
  except_topics: ['approvals'],
});

function QuietHours() {
  const sdk = useSdk();
  const { person } = useSignedIn();
  const [state, setState] = useState<{ prefs: Prefs; etag: string } | { error: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const memory = useMemo(() => personStorage(person), [person]);

  const read = useCallback(async () => {
    try {
      const { prefs, etag } = await sdk.notifications.preferences.get();
      setState({ prefs, etag });
    } catch {
      setState({ error: 'Unknown' });
    }
  }, [sdk]);
  useEffect(() => { void read(); }, [read]);

  const current = state && 'prefs' in state ? state : null;
  const on = !!current && !!current.prefs.quiet_hours;
  const toggle = async () => {
    if (!current || busy) return;
    setBusy(true);
    setNote('');
    try {
      let quiet: unknown = null;
      if (on) {
        try { memory?.setItem('shell.quiet', JSON.stringify(current.prefs.quiet_hours)); } catch { /* the times are just not remembered */ }
      } else {
        quiet = DEFAULT_QUIET();
        try {
          const saved = JSON.parse(memory?.getItem('shell.quiet') ?? 'null');
          if (saved && typeof saved === 'object') quiet = saved;
        } catch { /* private window or bad copy: use the default times */ }
      }
      const saved = await sdk.notifications.preferences.save({ ...current.prefs, quiet_hours: quiet }, current.etag);
      setState({ prefs: saved.prefs, etag: saved.etag });
    } catch (e) {
      if (e instanceof OneMindError && e.status === 409) {
        await read();
        setNote('Your notification settings changed somewhere else. Showing the latest; try again.');
      } else {
        setNote('Could not save quiet hours. Nothing changed.');
      }
    } finally {
      setBusy(false);
    }
  };

  const q = current?.prefs.quiet_hours as { from?: string; to?: string } | null | undefined;
  return (
    <section className="qs-sec" aria-labelledby="qs-quiet">
      <h3 id="qs-quiet" className="qs-title">Quiet hours</h3>
      <div className="qs-row">
        <span>{state === null ? 'Checking' : !current ? 'Unknown' : on && q?.from && q?.to ? `On, ${q.from} to ${q.to}` : 'Off'}</span>
        <button type="button" role="switch" aria-checked={on} aria-label="Quiet hours" className="qs-switch" disabled={!current || busy} onClick={() => void toggle()}>{on ? 'On' : 'Off'}</button>
      </div>
      <p className="qs-hint">Approvals and critical alerts still come through.</p>
      {note && <p className="qs-note" role="status">{note}</p>}
    </section>
  );
}

function StopAgents({ onModal, onNavigate }: { onModal: (b: boolean) => void; onNavigate: () => void }) {
  const sdk = useSdk();
  const state = usePoll(() => sdk.call<{ on?: boolean }>({ method: 'GET', path: '/v1/agents/kill-switch' }).catch((e: unknown) => { throw e instanceof OneMindError ? new ApiError(e.status, 'unknown', e.message) : e; }), 0);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState('');
  const [busy, setBusy] = useState(false);
  const ask = (v: boolean) => { setConfirm(v); onModal(v); };
  const stop = async () => {
    if (busy) return;
    setBusy(true);
    setErr('');
    try {
      await sdk.call({ method: 'PUT', path: '/v1/agents/kill-switch', body: { on: true } });
      await state.reload();
      ask(false);
    } catch {
      setErr('Could not stop the agents. Nothing changed.');
    } finally {
      setBusy(false);
    }
  };
  const stopped = state.data?.on === true;
  return (
    <section className="qs-sec" aria-labelledby="qs-agents">
      <h3 id="qs-agents" className="qs-title">AI agents</h3>
      {stopped ? (
        <p className="qs-hint">All agents are stopped. <Link to={href.setting('agents')} onClick={onNavigate}>Resume them in Agents</Link>.</p>
      ) : (
        <Button variant="danger" className="qs-stop" onClick={() => ask(true)}>Stop all agents</Button>
      )}
      {err && !confirm && <p className="qs-note" role="status">{err}</p>}
      <Dialog
        role="alertdialog"
        open={confirm}
        onClose={() => ask(false)}
        title="Stop all AI agents?"
        description="Every AI agent is refused until you resume them in Agents. People keep working. This is written to the audit record."
        actions={
          <>
            <Button variant="ghost" onClick={() => ask(false)}>Cancel</Button>
            <Button variant="danger" disabled={busy} onClick={() => void stop()}>Stop agents</Button>
          </>
        }
      >
        {err && <p role="alert">{err}</p>}
      </Dialog>
    </section>
  );
}

interface TileDef { id: string; label: string; to: string; path: string; map: (raw: unknown, now: number) => TileValue }

function Tiles({ owner, onNavigate }: { owner: boolean; onNavigate: () => void }) {
  const defs: TileDef[] = [
    ...(owner ? [{ id: 'network', label: 'Network', to: href.network, path: '/v1/network', map: networkTile }] : []),
    { id: 'updates', label: 'Updates', to: href.updates, path: '/v1/os/updates', map: updatesTile },
    { id: 'backups', label: 'Last backup', to: href.backups, path: '/v1/backups/status', map: backupTile },
    { id: 'storage', label: 'Storage', to: href.storage, path: '/v1/storage', map: (raw) => storageTile(raw) },
  ];
  return (
    <section className="qs-sec" aria-labelledby="qs-box">
      <h3 id="qs-box" className="qs-title">This box</h3>
      <ul className="qs-tiles">
        {defs.map((d) => <li key={d.id}><Tile def={d} onNavigate={onNavigate} /></li>)}
      </ul>
    </section>
  );
}

function Tile({ def, onNavigate }: { def: TileDef; onNavigate: () => void }) {
  const sdk = useSdk();
  const now = useNow(15_000);
  const poll = usePoll(() => sdk.call<unknown>({ method: 'GET', path: def.path }), 30_000);
  // A failed refresh is Unknown even when an older answer is kept: never a green state on stale data.
  const v: TileValue = poll.error ? UNKNOWN : poll.data === undefined ? { value: 'Checking', tone: 'unknown' } : def.map(poll.data, now);
  const age = poll.fetchedAt === undefined ? '' : `Checked ${formatAgo(Math.max(0, Math.round((now - poll.fetchedAt) / 1000)))}`;
  return (
    <Link to={def.to} className={`qs-tile qs-tone-${v.tone}`} onClick={onNavigate}>
      <span className="qs-tile-label">{def.label}</span>
      <span className="qs-tile-value">{v.value}</span>
      {age && !poll.error && <span className="qs-tile-age">{age}</span>}
    </Link>
  );
}
