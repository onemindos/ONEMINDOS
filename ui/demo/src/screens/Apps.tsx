// SPDX-License-Identifier: Apache-2.0
// Apps and Market (IA §2.2): installed apps first, then the scan-gated catalogue.
import { useState } from 'react';
import { Button, Card, Icon, PageHeader, StatusPill, installBlockReason, useToast } from '../../../src';
import { AppIcon, Section } from '../bits';
import { NOW, apps, type DemoApp } from '../fixtures';

const CATS = ['All', 'home', 'automation', 'monitoring', 'notifications', 'security', 'media', 'ai'];

function AppCard({ app }: { app: DemoApp }) {
  const toast = useToast();
  const block = app.installed ? undefined : installBlockReason(app.scan, app.tier, NOW);
  const noFit = !app.installed && !block && app.why ? 'No node has enough free memory.' : undefined;
  const reason = block ?? noFit;
  return (
    <Card
      level={3}
      title={
        <a href={`#/app/${app.id}`} className="d-appcard-top" style={{ color: 'inherit', textDecoration: 'none' }}>
          <AppIcon app={app} />
          <span>{app.name}</span>
        </a>
      }
      aside={
        app.installed ? (
          <StatusPill tone="ok" label="Installed" />
        ) : app.tier === 'blocked' ? (
          <StatusPill tone="bad" label="Blocked" />
        ) : (
          <StatusPill tone={app.tier === 'verified' ? 'ok' : 'neutral'} label={app.tier === 'verified' ? 'Verified' : 'Community'} dot={false} />
        )
      }
      footer={
        <div className="d-row">
          {app.installed ? (
            <Button size="sm" icon="external">Open</Button>
          ) : (
            <Button
              size="sm"
              variant="primary"
              icon="plus"
              disabled={!!reason}
              aria-describedby={reason ? `why-${app.id}` : undefined}
              onClick={() => toast.show({ tone: 'info', title: `Install ${app.name} requested`, body: 'It is waiting in Approvals.', action: { label: 'View', onClick: () => (window.location.hash = '#/approvals') } })}
            >
              Request install
            </Button>
          )}
          <a href={`#/app/${app.id}`} className="om-hint">Details</a>
          {reason && (
            <span id={`why-${app.id}`} className="om-hint">
              {reason}
            </span>
          )}
        </div>
      }
    >
      <p className="d-appcard-desc">{app.description}</p>
      <p className="om-hint">
        {app.license} · {app.archs.join(', ')} · {app.requires?.minMemoryMb} MB
      </p>
    </Card>
  );
}

export function Apps() {
  const [cat, setCat] = useState('All');
  const shown = apps.filter((a) => cat === 'All' || a.category === cat);
  return (
    <>
      <PageHeader
        title="Apps"
        lede="Every app in the Market passed a licence check, a vulnerability scan and a malware scan in the last 7 days. Installing asks for approval first."
        actions={<Button icon="plus">Deploy your own</Button>}
      />
      <div className="d-row">
        <label className="d-search">
          <Icon name="search" size={18} />
          <span className="om-visually-hidden">Search apps</span>
          <input type="search" placeholder="Search apps" />
        </label>
      </div>
      <div className="d-row" role="group" aria-label="Category">
        {CATS.map((c) => (
          <button key={c} type="button" className="d-chip" aria-pressed={cat === c} onClick={() => setCat(c)}>
            {c === 'All' ? 'All' : c[0]!.toUpperCase() + c.slice(1)}
          </button>
        ))}
      </div>
      <Section title="Installed">
        <div className="d-grid">
          {shown.filter((a) => a.installed).map((a) => (
            <AppCard key={a.id} app={a} />
          ))}
        </div>
      </Section>
      <Section title="Market">
        <div className="d-grid">
          {shown.filter((a) => !a.installed).map((a) => (
            <AppCard key={a.id} app={a} />
          ))}
        </div>
      </Section>
    </>
  );
}
