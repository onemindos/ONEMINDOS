// SPDX-License-Identifier: Apache-2.0
import { useMemo, useState } from 'react';
import { Link } from 'react-router';
import { OneMind, type components, type paths } from '@onemind/sdk';
import { Button, Card, EmptyState, StatusPill } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { href } from '../shell/routes';
import { useShell } from '../shell/Shell';
import { read, useFiling } from './backups/shared';
import { Load } from './parts';

type Check = components['schemas']['CareCheck'];
const titles: Record<Check['id'], string> = {
  backup: 'Data without a backup', probe: 'Missing health probes', scan: 'Stale app scans',
  ownership: 'Workloads without an app', image: 'Unpinned images', disk: 'Low disk space', drill: 'Overdue restore drill',
};
const endpoint = '/v1/care/checkup' satisfies keyof paths;

export function Care() {
  const { role } = useShell();
  const { mock, token, person } = useSignedIn();
  if (role !== 'owner') return <EmptyState icon="lock" title="Owner access required">Only the owner can inspect this box.</EmptyState>;
  if (mock) return <EmptyState icon="info" title="Box check-up unavailable">Connect to your hub to inspect its health.</EmptyState>;
  return <LiveCare key={person} token={token} />;
}

function LiveCare({ token }: { token: string }) {
  const sdk = useMemo(() => new OneMind({ baseUrl: window.location.origin, token }), [token]);
  const report = usePoll(async () => {
    const data = await read(sdk, endpoint);
    if (!Array.isArray(data) || !data.every(row => row && Object.hasOwn(titles, row.id)
      && ['finding', 'unavailable', 'clear'].includes(row.state) && typeof row.detail === 'string')) {
      throw new Error('The hub returned an invalid check-up.');
    }
    return data as Check[];
  }, 0);
  const { file, busy, error } = useFiling(sdk, token);
  const [receipt, setReceipt] = useState('');
  const request = async () => {
    const filed = await file('/v1/backups/runs', 'backup.run', { scope: 'box', approve: false } satisfies components['schemas']['RunBody']);
    if (filed) setReceipt(filed.id);
  };
  return <section className="dash-stack" aria-label="Box check-up">
    <h2>Box check-up</h2>
    <Button variant="secondary" disabled={report.loading} onClick={() => void report.reload()}>Refresh check-up</Button>
    {report.error && report.data && <p role="alert">Refresh failed. Showing the previous check-up.</p>}
    <Load res={report} what="Box check-up">{checks => checks.map(check =>
      <Card key={check.id} title={titles[check.id]} aside={<StatusPill
        tone={check.state === 'finding' ? 'warn' : check.state === 'clear' ? 'ok' : 'neutral'}
        label={check.state === 'finding' ? 'Needs attention' : check.state === 'clear' ? 'Clear' : 'Unavailable'} />}>
        <p>{check.detail}</p>
        {check.fix === 'backup.run' && check.state === 'finding' && !receipt && <Button disabled={busy || !!report.error}
          onClick={() => void request()}>Request a whole-box backup</Button>}
      </Card>)}</Load>
    {error && <p role="alert">{error}</p>}
    {receipt && <p role="status">Backup request filed. <Link to={href.approval(receipt)}>View approval request</Link></p>}
  </section>;
}
