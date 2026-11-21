// SPDX-License-Identifier: Apache-2.0
// Settings, About this box (UMB-P14, #432): the device facts from GET /v1/os/about, per node, and a
// Copy details button for support requests. The copied text has no serial numbers or addresses (the
// box never reports them) and no node id unless the owner ticks the box.
import { useState } from 'react';
import { Button, Card } from '@onemind/ui';
import { usePoll } from '../lib/hooks';
import { useSignedIn } from '../session';
import { aboutText, nodeFacts } from '../lib/aboutText';

export function AboutBox() {
  const { api } = useSignedIn();
  const about = usePoll(async () => (api.about ? api.about() : Promise.reject(new Error('unsupported'))), 30_000);
  const [ids, setIds] = useState(false);
  const [copied, setCopied] = useState<'done' | 'failed'>();

  if (!api.about)
    return <p className="om-hint">Demo mode has no device data. A real hub reports the box it runs on here (GET /v1/os/about).</p>;
  // A person without nodes:read (a child) gets 403 from the hub: say so, not "could not read".
  if (about.error?.status === 403) return <p className="om-hint">Device details are not available for your account.</p>;
  if (!about.data)
    return <p className="om-hint">{about.error ? `Could not read the device details: ${about.error.message}` : 'Loading the device details…'}</p>;

  const data = about.data;
  const text = aboutText(data, ids);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied('done');
    } catch {
      setCopied('failed');
    }
  };
  return (
    <>
      <h2 className="om-h2">About this box</h2>
      <p className="om-hint">
        {data.node_count} node{data.node_count === 1 ? '' : 's'} reporting. From the machines' own heartbeats; the version and slot are the ones the update service reports.
      </p>
      {data.nodes.map((n) => (
        <Card key={n.node_id} title={`${n.hostname ?? n.node_id}${n.node_id === data.hub_node_id ? ' (hub)' : ''}`} level={3}>
          <dl className="om-facts">
            {nodeFacts(n).map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd>{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      ))}
      <Card title="Copy details for a support request" level={3}>
        <p className="om-hint">Leaves out serial numbers and addresses: this box does not report them. The node id is left out too unless you turn it on.</p>
        <label>
          <input type="checkbox" checked={ids} onChange={(e) => setIds(e.target.checked)} /> Include the node id
        </label>
        <pre className="om-code" aria-label="Text that will be copied">{text}</pre>
        <Button onClick={copy}>Copy details</Button>
        {copied === 'done' && <p role="status" className="om-hint">Copied.</p>}
        {copied === 'failed' && <p role="alert" className="om-hint">Could not reach the clipboard. Select the text above and copy it.</p>}
      </Card>
    </>
  );
}
