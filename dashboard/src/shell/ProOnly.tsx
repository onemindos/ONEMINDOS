// SPDX-License-Identifier: Apache-2.0
// Guards a Pro screen (roles.ts). A guest or child who follows a link here gets a calm line and a
// way home instead of a screen of errors; the gateway refuses the data either way.
import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { Card, PageHeader, StateView } from '@onemind/ui';
import { href } from './routes';
import { useShell } from './Shell';

export function ProOnly({ title, children }: { title: string; children: ReactNode }) {
  const { view } = useShell();
  if (view === 'pro') return <>{children}</>;
  if (view === 'unknown') return <StateView state="loading" what="Checking your role" skeleton="list" />;
  return (
    <div className="dash-stack">
      <PageHeader title={title} />
      <Card variant="sunken">
        <p role="status">This screen is for the people who run this box (owners and adults). Ask an owner if you need something here.</p>
        <p>
          <Link to={href.home}>Back to Home</Link>
        </p>
      </Card>
    </div>
  );
}
