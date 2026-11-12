import { useState } from 'react';
import { useSearchParams } from 'react-router';
import { ApiError, type Action } from '../api/types';
import { ErrorNote, KindBadge, Loading } from '../components/bits';
import { useNow, usePoll } from '../lib/hooks';
import { formatAgo, formatIn, secondsSince } from '../lib/time';
import { useSignedIn } from '../session';

const TYPE_VERB: Record<string, string> = { 'app.install': 'Install', 'app.remove': 'Remove' };

function title(a: Action) {
  return `${TYPE_VERB[a.type] ?? a.type} ${a.params.app_id}`;
}

function ActionCard({
  action,
  now,
  highlight,
  onDecide,
  busy,
  canDecide,
}: {
  action: Action;
  now: number;
  highlight: boolean;
  onDecide?: (a: Action, d: 'approve' | 'deny') => void;
  busy: boolean;
  canDecide: 'yes' | 'no' | 'unknown';
}) {
  const expired = Date.parse(action.expires_at) <= now;
  const id = `action-${action.id}`;
  const pending = action.state === 'awaiting_approval';
  const disabled = busy || canDecide === 'no' || expired;
  return (
    <li>
      <article className={`action-card ${highlight ? 'action-new' : ''}`} aria-labelledby={id}>
        <header className="node-head">
          <h3 id={id}>{title(action)}</h3>
          <span className={`badge badge-state-${action.state}`}>{action.state.replace(/_/g, ' ')}</span>
        </header>
        <p className="requester">
          Requested by <KindBadge kind={action.requested_by?.kind} /> <strong>{action.requested_by?.id ?? 'unknown'}</strong>
          {action.requested_by?.role ? ` (${action.requested_by.role})` : ''}
          {action.created_at ? `, ${formatAgo(secondsSince(action.created_at, now))}` : ''}
        </p>
        <dl className="facts facts-compact">
          <div>
            <dt>Action type</dt>
            <dd>
              <code>{action.type}</code>
            </dd>
          </div>
          <div>
            <dt>Expires</dt>
            <dd>
              {pending ? <strong>{formatIn(action.expires_at, now)}</strong> : formatIn(action.expires_at, now)}{' '}
              <span className="small">({action.expires_at})</span>
            </dd>
          </div>
          <div>
            <dt>Idempotency key</dt>
            <dd>
              <code>{action.idempotency_key}</code>
            </dd>
          </div>
        </dl>
        <p className="small params-label">Exact parameters</p>
        <pre className="params">
          {JSON.stringify(action.params, null, 2)}
        </pre>
        {pending && onDecide && (
          <div className="decide">
            <button
              type="button"
              className="btn btn-primary"
              disabled={disabled}
              aria-label={`Approve ${title(action)}`}
              onClick={() => onDecide(action, 'approve')}
            >
              Approve
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={disabled}
              aria-label={`Deny ${title(action)}`}
              onClick={() => onDecide(action, 'deny')}
            >
              Deny
            </button>
            {expired && <span className="small">This request has expired and can no longer be approved.</span>}
          </div>
        )}
      </article>
    </li>
  );
}

export function Approvals() {
  const { api, canDecide, markForbidden } = useSignedIn();
  const now = useNow();
  const [params] = useSearchParams();
  const highlight = params.get('highlight');
  const actions = usePoll(() => api.actions(), 5_000);
  const [busy, setBusy] = useState<string>();
  const [message, setMessage] = useState<{ text: string; error: boolean }>();
  // Decisions the hub has confirmed. An action never returns to awaiting_approval,
  // so a list fetched before the decision must not bring back live buttons.
  const [decided, setDecided] = useState<Record<string, Action>>({});

  async function decide(a: Action, d: 'approve' | 'deny') {
    setBusy(a.id);
    setMessage(undefined);
    try {
      const res = d === 'approve' ? await api.approve(a.id) : await api.deny(a.id);
      setDecided((m) => ({ ...m, [res.id]: res }));
      setMessage({ text: `${title(a)}: ${res.state.replace(/_/g, ' ')}.`, error: false });
    } catch (e) {
      if (e instanceof ApiError && e.code === 'permission_denied') {
        markForbidden();
        setMessage({ text: 'Only the owner can approve or deny requests.', error: true });
      } else if (e instanceof ApiError && e.code === 'expired') {
        setMessage({ text: `${title(a)} expired before it was approved.`, error: true });
      } else {
        setMessage({ text: `Could not ${d}: ${e instanceof Error ? e.message : String(e)}`, error: true });
      }
    } finally {
      await actions.reload();
      setBusy(undefined);
    }
  }

  const all = (actions.data ?? []).map((a) => (a.state === 'awaiting_approval' && decided[a.id]) || a);
  const pending = all.filter((a) => a.state === 'awaiting_approval');
  const history = all.filter((a) => a.state !== 'awaiting_approval');

  return (
    <div className="page">
      <h1>Approvals</h1>
      <p className="lede">
        Every change to this OneMind waits here for the owner. AI agents can ask, but only a person who owns the box can
        say yes.
      </p>
      {canDecide === 'no' && <p className="note">You can see requests, but only the owner can approve or deny them.</p>}
      {canDecide === 'unknown' && (
        <p className="note">The hub checks that you are the owner when you approve or deny.</p>
      )}
      <div aria-live="polite" role="status">
        {message && <p className={`note ${message.error ? 'note-error' : 'note-ok'}`}>{message.text}</p>}
      </div>
      {actions.error && <ErrorNote error={actions.error} fetchedAt={actions.fetchedAt} now={now} />}
      <section aria-labelledby="pending-title">
        <h2 id="pending-title">Waiting for approval ({pending.length})</h2>
        {actions.loading && !actions.data ? (
          <Loading what="requests" />
        ) : pending.length === 0 ? (
          <p>Nothing is waiting.</p>
        ) : (
          <ul className="stack">
            {pending.map((a) => (
              <ActionCard
                key={a.id}
                action={a}
                now={now}
                highlight={a.id === highlight}
                onDecide={(x, d) => void decide(x, d)}
                busy={busy !== undefined}
                canDecide={canDecide}
              />
            ))}
          </ul>
        )}
      </section>
      {history.length > 0 && (
        <section aria-labelledby="history-title">
          <h2 id="history-title">History</h2>
          <ul className="stack">
            {history.map((a) => (
              <ActionCard key={a.id} action={a} now={now} highlight={false} busy={false} canDecide={canDecide} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
