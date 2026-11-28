// SPDX-License-Identifier: Apache-2.0
// Settings > About, rename this box (P-05): PUT /v1/instance/name files a request; nothing changes until an
// owner approves it in Approvals (D-027). Once the box has done it, it answers as <name>.local and the
// sign-in page says the new name. Owner only; absent in demo mode, which has no host to rename.
import { useState, type FormEvent } from 'react';
import { Link } from 'react-router';
import { Button, Card } from '@onemind/ui';
import { useSignedIn } from '../session';
import { TextField, useRun } from './parts';

/** One lower-case DNS label, as the gateway checks it (core/onemind_core/routers/instance_name.py). */
export const BOX_NAME = /^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$/;

export function RenameBoxCard({ current }: { current?: string }) {
  const { api, principal } = useSignedIn();
  const run = useRun();
  const [name, setName] = useState('');
  const [pending, setPending] = useState<{ id: string; name: string }>();
  const [busy, setBusy] = useState(false);
  if (!api.renameInstance || principal?.role !== 'owner') return null;
  const rename = api.renameInstance.bind(api);
  const typed = name.trim();
  const bad = typed !== '' && !BOX_NAME.test(typed);
  const same = typed !== '' && typed === current;
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !typed || bad || same) return;
    setBusy(true);
    try {
      const action = await run(() => rename(typed), 'Rename this box');
      if (action) {
        setPending({ id: action.id, name: typed });
        setName('');
      }
    } finally {
      setBusy(false);
    }
  };
  return (
    <Card title="Rename this box">
      <form className="dash-form" onSubmit={(e) => void submit(e)}>
        <TextField id="box-name" label="Box name" value={name} onChange={setName} />
        <p id="box-name-hint" className="om-hint">
          Lower-case letters, digits and dashes, up to 63 characters. Other devices will find this box at <code>{typed && !bad ? typed : 'name'}.local</code>; bookmarks to the old name stop working.
        </p>
        {bad && <p role="alert">Use only lower-case letters, digits and dashes, and do not start or end with a dash.</p>}
        {same && <p role="status" className="om-hint">That is already this box's name.</p>}
        <Button type="submit" disabled={busy || !typed || bad || same}>Request rename</Button>
      </form>
      {pending && (
        <p role="status">
          Renaming to <strong>{pending.name}</strong> was requested. <Link to="/approvals">Approve it in Approvals</Link> and the box takes the new name within a few seconds.
        </p>
      )}
    </Card>
  );
}
