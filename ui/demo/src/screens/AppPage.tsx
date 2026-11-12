// SPDX-License-Identifier: Apache-2.0
// App page (IA §2.3): what it is, can I trust it, what does it do on my box, and its lifecycle.
import { useState } from 'react';
import { Button, Card, Dialog, PageHeader, StatusPill, Table, TrustCard, installBlockReason, useToast } from '../../../src';
import { AppIcon } from '../bits';
import { NOW, apps, nodes } from '../fixtures';

export function AppPage({ id }: { id: string }) {
  const app = apps.find((a) => a.id === id) ?? apps[0]!;
  const toast = useToast();
  const [confirm, setConfirm] = useState(false);
  const blocked = !app.installed && (installBlockReason(app.scan, app.tier, NOW) !== undefined || !!app.why);
  const placement = app.installed ? { node: app.node ?? null } : app.why ? { node: null, reasons: app.why } : { node: nodes[0]!.hostname };
  return (
    <>
      <div className="d-row" style={{ gap: 'var(--om-space-4)' }}>
        <AppIcon app={app} size={64} />
        <PageHeader
          title={app.name}
          lede={
            <>
              {app.description}{' '}
              {app.installed && <StatusPill tone="ok" label="Running" detail={`on ${app.node}`} />}
            </>
          }
        />
      </div>
      <div className="d-row">
        {app.installed ? (
          <>
            <Button variant="primary" icon="external">Open</Button>
            {app.updateAvailable && (
              <Button icon="updates" onClick={() => toast.show({ tone: 'info', title: `Update to ${app.updateAvailable} requested`, body: 'A snapshot is taken first. It reverts by itself if the app is unhealthy.' })}>
                Update to {app.updateAvailable}
              </Button>
            )}
            <Button icon="updates">Restart</Button>
            <Button variant="ghost" onClick={() => setConfirm(true)}>Remove…</Button>
          </>
        ) : (
          <>
            <Button variant="primary" icon="plus" disabled={blocked} aria-describedby={blocked ? 'install-why' : undefined}>
              Request install
            </Button>
            {blocked && (
              <span id="install-why" className="om-hint">
                See “Trust and fit” for why.
              </span>
            )}
          </>
        )}
      </div>
      <div className="d-grid-2">
        <div className="d-stack">
          {app.installed && (
            <Card title="Settings" subtitle="Panel provided by the app (plugin extension point, sandboxed)">
              <div className="d-plugin-frame">
                <StatusPill tone="agent" label={`From ${app.name} · sandboxed`} dot={false} className="d-plugin-tag" />
                <label className="d-field">
                  Time zone
                  <select defaultValue="UTC">
                    <option>UTC</option>
                    <option>Europe/Berlin</option>
                  </select>
                </label>
                <label className="d-field">
                  External URL
                  <input defaultValue={`https://${app.id}.home-hub.local`} />
                  <span className="d-field-hint">Changing a setting is a request; you approve it like any other.</span>
                </label>
              </div>
            </Card>
          )}
          {app.installed && (
            <Card title="Data and backup">
              <dl className="d-kv">
                <dt>Volumes</dt>
                <dd>config (2.1 GB) · media (excluded from backup)</dd>
                <dt>Last backup</dt>
                <dd>41 min ago · restore verified 1 d ago</dd>
                <dt>Database</dt>
                <dd>SQLite, copied consistently before each backup</dd>
              </dl>
            </Card>
          )}
          {app.installed && (
            <Card title="Logs" subtitle="Last 6 lines · live" aside={<Button size="sm">Download</Button>}>
              <pre className="d-logs">{`14:58:12 INFO  Started web server on :8123
14:58:13 INFO  Loaded 24 integrations
14:59:40 WARN  Device 'garage-door' not seen for 300 s
14:59:58 INFO  Automation 'lights-off' triggered
15:00:00 INFO  Recorder purge done (12 ms)
15:00:01 INFO  Health check ok`}</pre>
            </Card>
          )}
          <Card title="History">
            <Table
              caption="Install and update history"
              hideCaption
              rowKey={(r) => r.at}
              columns={[
                { key: 'at', header: 'When' },
                { key: 'what', header: 'What' },
                { key: 'by', header: 'Approved by', secondary: true },
                { key: 'res', header: 'Result', render: (r) => <StatusPill tone={r.tone} label={r.res} /> },
              ]}
              rows={
                app.installed
                  ? [
                      { at: '5 d ago', what: `Installed ${app.version}`, by: 'person:owner', res: 'Healthy', tone: 'ok' as const },
                      { at: '19 d ago', what: 'Update reverted', by: 'person:owner', res: 'Reverted', tone: 'warn' as const },
                    ]
                  : []
              }
              empty={<p className="om-hint">Not installed on this box yet.</p>}
            />
          </Card>
        </div>
        <div className="d-stack">
          <TrustCard app={app} now={NOW} placement={app.installed ? undefined : placement} />
        </div>
      </div>
      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        role="alertdialog"
        title={`Remove ${app.name}?`}
        description="The app stops and its namespace is deleted. Its data volumes are kept, so installing it again brings your data back. This is a request; you approve it next."
        actions={
          <>
            <Button onClick={() => setConfirm(false)}>Cancel</Button>
            <Button
              variant="danger"
              onClick={() => {
                setConfirm(false);
                toast.show({ tone: 'info', title: `Remove ${app.name} requested`, body: 'Data will be kept.' });
              }}
            >
              Request removal
            </Button>
          </>
        }
      />
    </>
  );
}
