// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState, type FormEvent } from 'react';
import { OneMindError, type OneMind, type OneMindEvent, type operations } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';

type CardReply = operations['me.dashboard_card.get']['responses'][200]['content']['application/json'];
type CardBody = operations['me.dashboard_card.save']['requestBody']['content']['application/json'];
const CARD_PATH = '/v1/me/dashboard-card';
const NOT_ALLOWED = 'Your account does not have access to this event source.';

function denied(error: unknown) {
  return error instanceof OneMindError && (error.status === 401 || error.status === 403);
}

function SubjectReading({ client, subject, reload }: { client: OneMind; subject: string; reload: () => Promise<void> }) {
  const [state, setState] = useState<{ event?: OneMindEvent; message?: string }>({});
  useEffect(() => {
    const controller = new AbortController();
    void client.events.subscribeDashboardCard({ signal: controller.signal }, (event) => {
      if (controller.signal.aborted) return;
      if (event.type === 'stream.reset') {
        if (event.data?.reason === 'subject_unavailable') {
          setState({ message: NOT_ALLOWED });
          controller.abort();
          void reload();
        } else {
          setState({ message: 'The event stream is reconnecting.' });
        }
        return;
      }
      setState({ event });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) {
        setState({ message: denied(error) ? NOT_ALLOWED : 'The gateway could not load card events.' });
      }
    });
    return () => controller.abort();
  }, [client, reload]);

  const { event } = state;
  return (
    <>
      <p>Source <code>{subject}</code></p>
      {event ? (
        <p>
          <strong>{event.type}</strong>
          {event.ts && <> · <time dateTime={event.ts}>{new Date(event.ts).toLocaleString()}</time></>}
          {event.severity && <> · {event.severity}</>}
        </p>
      ) : (
        <p role="status">{state.message ?? 'Waiting for a matching event.'}</p>
      )}
    </>
  );
}

export function SubjectCardPanel({ client }: { client: OneMind }) {
  const res = usePoll(async () => {
    try {
      return { card: await client.call<CardReply>({ method: 'GET', path: CARD_PATH }) };
    } catch (error) {
      if (denied(error)) return { denied: true } as const;
      throw error;
    }
  }, 0);
  const [subject, setSubject] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const current = res.data?.card?.source.subject;

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      const body: CardBody = { source: { kind: 'subject', subject } };
      await client.call({ method: 'PUT', path: CARD_PATH, body });
      await res.reload();
      setSubject('');
    } catch (error) {
      setMessage(denied(error) ? NOT_ALLOWED
        : error instanceof OneMindError && error.reason === 'bad_subject'
          ? 'Choose a gateway node or backup subject. Use at most one * in the event name.'
          : 'The gateway could not save this event source.');
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card title="Event card">
      {res.data?.denied && <p role="status">{NOT_ALLOWED}</p>}
      {res.error && <p role="status">The gateway could not load this card.</p>}
      {current && <SubjectReading key={current} client={client} subject={current} reload={res.reload} />}
      <form className="dash-actions" onSubmit={(event) => void save(event)}>
        <label>
          Event subject{' '}
          <input required value={subject} onChange={(event) => setSubject(event.target.value)}
            placeholder="onemind.event.backup.run.finished" />
        </label>
        <Button type="submit" disabled={saving || !subject}>Save event source</Button>
      </form>
      {message && <p role="status">{message}</p>}
    </Card>
  );
}
