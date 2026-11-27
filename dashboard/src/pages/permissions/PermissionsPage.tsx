// SPDX-License-Identifier: Apache-2.0
// Settings > Permissions (gateway permissions design §3.12, row "Settings → Permissions"). One page,
// one tab per question a first-time owner asks: who has access, how each requester's requests are
// handled (Modes), and the rules that answer for you. Each tab has its own address
// (/settings/permissions/<tab>) so a notification can open it directly.
import type { ComponentType } from 'react';
import { Link, useParams } from 'react-router';
import { PageHeader } from '@onemind/ui';
import { WhoHasAccess } from '../SettingsSecurity';
import { AutoApproved } from './AutoApproved';
import { Modes } from './Modes';
import { Never } from './Never';
import { Rules } from './Rules';

export interface PermissionsTab {
  id: string;
  label: string;
  Body: ComponentType<{ item?: string }>;
}

export const TABS: PermissionsTab[] = [
  { id: 'modes', label: 'Modes', Body: Modes },
  { id: 'rules', label: 'Rules', Body: Rules },
  { id: 'never', label: 'Never', Body: Never },
  { id: 'auto-approved', label: 'Auto-approved', Body: AutoApproved },
  { id: 'access', label: 'Who has access', Body: WhoHasAccess },
];

export function PermissionsPage() {
  const { tab, item } = useParams();
  const current = TABS.find((t) => t.id === tab) ?? TABS[0]!;
  const Body = current.Body;
  return (
    <>
      <PageHeader
        title="Permissions"
        lede="Nothing on your box changes until a person approves it. Here you choose which requests wait for you, which are refused, and which your own rules may answer for you."
      />
      <nav aria-label="Permissions sections" className="om-set-chips">
        {TABS.map((t) => (
          <Link key={t.id} to={`/settings/permissions/${t.id}`} className="om-set-chip" aria-current={t.id === current.id ? 'page' : undefined}>
            {t.label}
          </Link>
        ))}
      </nav>
      <Body key={current.id} item={item} />
    </>
  );
}
