// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from 'react';
import type { components, OneMind, StatusView } from '@onemind/sdk';
import { Button, Card } from '@onemind/ui';
import { useBusy, useRun } from '../parts';

type Bundle = components['schemas']['DiagnosticsBundle'];

// Only these public check names may leave the page. Status summaries and arbitrary bundle keys
// can contain private data, as can the gateway's free-form fields.
export const CHECKS = ['alerts', 'approvals', 'apps', 'storage', 'backups', 'updates', 'mesh'] as const;

function publicIssue(text: string, bundle: Bundle, status?: StatusView) {
  const lines = [text];
  const version = bundle.gateway?.version;
  if (typeof version === 'string' && /^\d{1,6}\.\d{1,6}\.\d{1,6}$/.test(version)) lines.push('OneMind version: ' + version);
  const failing = CHECKS.filter(check => ['critical', 'attention'].includes(status?.[check]?.state ?? ''));
  if (failing.length) lines.push('Failing checks: ' + failing.join(', '));
  const url = new URL('https://github.com/onemindos/ONEMINDOS/issues/new');
  url.searchParams.set('body', lines.join('\n\n'));
  return url.href;
}

export function saveJson(name: string, data: unknown) {
  const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }));
  try {
    const a = document.createElement('a');
    a.href = url;
    a.download = name;
    a.click();
  } finally {
    URL.revokeObjectURL(url);
  }
}

export function ReportProblem({ client, status }: { client: OneMind; status?: StatusView }) {
  const id = useId();
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<{ bundle: Bundle; issue: string }>();
  const [busy, withBusy] = useBusy();
  const run = useRun();
  const collect = () => void withBusy(() => run(async () => {
    const bundle = await client.call<Bundle>({ method: 'GET', path: '/v1/system/diagnostics' });
    if (!bundle?.redaction?.found) throw new Error('The box returned an incomplete diagnostic bundle.');
    setPreview({ bundle, issue: publicIssue(text, bundle, status) });
  }, 'Could not preview the report'));

  return <Card title="Report a problem">
    {preview ? <>
      <h3>Report preview</h3>
      <p>{text}</p>
      <p>Redaction summary: {Object.entries(preview.bundle.redaction.found).map(([rule, count]) => count + ' ' + rule).join(', ') || 'Nothing removed'}.</p>
      {Object.entries(preview.bundle).map(([key, value]) => <details key={key}>
        <summary>{key}</summary>
        <pre>{JSON.stringify(value, null, 2)}</pre>
      </details>)}
      <p>The saved report includes your description and the bundle. The public issue opens on GitHub with your description, the available version and failing check names. You choose whether to attach the file.</p>
      <Button onClick={() => saveJson('onemind-report-' + new Date().toISOString().slice(0, 10) + '.json', { text, bundle: preview.bundle })}>Save report</Button>{' '}
      <a href={preview.issue} target="_blank" rel="noopener noreferrer">Open a public issue</a>{' '}
      <Button variant="ghost" onClick={() => setPreview(undefined)}>Edit description</Button>
    </> : <>
      <label htmlFor={id}>What happened?</label>
      <textarea id={id} value={text} onChange={event => setText(event.target.value)} disabled={busy} />
      <Button busy={busy} disabled={!text.trim()} onClick={collect}>Preview report</Button>
    </>}
  </Card>;
}
