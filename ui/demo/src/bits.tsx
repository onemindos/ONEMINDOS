// SPDX-License-Identifier: Apache-2.0
// Demo-only helpers. Candidates for the library once a second screen needs them.
import type { ReactNode } from 'react';
import { StatusPill, type Tone } from '../../src';
import type { DemoApp } from './fixtures';

export function AppIcon({ app, size = 44 }: { app: Pick<DemoApp, 'name' | 'colour'>; size?: number }) {
  return (
    <span className={`d-appicon d-hue-${app.colour}`} style={{ width: size, height: size, fontSize: size * 0.42 }} aria-hidden="true">
      {app.name[0]}
    </span>
  );
}

export function Stat({ label, value, detail, tone, href }: { label: string; value: ReactNode; detail?: ReactNode; tone?: Tone; href?: string }) {
  const body = (
    <>
      <span className="d-stat-label">{label}</span>
      <span className="d-stat-value">{value}</span>
      {detail && <span className="d-stat-detail">{tone ? <StatusPill tone={tone} label={String(detail)} /> : detail}</span>}
    </>
  );
  return href ? (
    <a className="d-stat d-stat-link" href={href}>
      {body}
    </a>
  ) : (
    <div className="d-stat">{body}</div>
  );
}

export function Section({ title, aside, children }: { title: string; aside?: ReactNode; children: ReactNode }) {
  const id = `sec-${title.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`;
  return (
    <section className="d-section" aria-labelledby={id}>
      <div className="d-section-head">
        <h2 id={id}>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export const ACTOR_TONE = { person: 'neutral', agent: 'agent', system: 'info' } as const;
