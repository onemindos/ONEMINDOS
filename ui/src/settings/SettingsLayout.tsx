// SPDX-License-Identifier: Apache-2.0
// Settings frame: grouped section list with search on the left, the section on the right.
// Phones drill in: the list is the index page, a section page has "All settings" to go back.
import { useId, useState, type ReactNode } from 'react';
import { cx } from '../lib/cx';
import { PageHeader } from '../components/AppShell';
import { StatusPill } from '../components/StatusPill';
import type { Tone } from '../tokens/tokens';
import { matchSection } from './logic';
import { SetIcon, type SetIconName } from './primitives';

export type SettingsSectionId = 'appearance' | 'account' | 'users' | 'devices' | 'network' | 'backups' | 'updates' | 'notifications' | 'automation' | 'agents' | 'storage' | 'about';

export interface SettingsSectionMeta {
  id: SettingsSectionId;
  label: string;
  icon: SetIconName;
  group: string;
  /** Extra words people search for. */
  keywords: string[];
}

export const SETTINGS_SECTIONS: SettingsSectionMeta[] = [
  { id: 'appearance', label: 'Appearance', icon: 'eye', group: 'You', keywords: ['theme', 'dark', 'light', 'accent', 'wallpaper', 'colour', 'color', 'density', 'font'] },
  { id: 'account', label: 'Account & security', icon: 'lock', group: 'People and access', keywords: ['passkey', 'password', 'sessions', 'tokens', 'sign in', '2fa', 'totp'] },
  { id: 'users', label: 'Users & roles', icon: 'users', group: 'People and access', keywords: ['people', 'family', 'invite', 'owner', 'guest'] },
  { id: 'agents', label: 'Agents & MCP', icon: 'agent', group: 'People and access', keywords: ['ai', 'hermes', 'mcp', 'tools', 'revoke', 'suspend'] },
  { id: 'devices', label: 'Devices & nodes', icon: 'nodes', group: 'Machines', keywords: ['fabric', 'join', 'qr', 'hub', 'worker', 'leaf', 'add node'] },
  { id: 'network', label: 'Network & mesh', icon: 'globe', group: 'Machines', keywords: ['remote', 'vpn', 'mesh', 'dns', 'mdns', 'certificate', 'https', 'tls'] },
  { id: 'storage', label: 'Storage', icon: 'disk', group: 'Machines', keywords: ['disk', 'space', 'usage', 'categories'] },
  { id: 'backups', label: 'Backups', icon: 'backups', group: 'Keeping it healthy', keywords: ['restore', 'snapshot', 'usb', 's3', 'emergency kit'] },
  { id: 'updates', label: 'Updates', icon: 'updates', group: 'Keeping it healthy', keywords: ['os', 'version', 'channel', 'rollback', 'release notes', 'slot'] },
  { id: 'notifications', label: 'Notifications', icon: 'bell', group: 'Keeping it healthy', keywords: ['push', 'email', 'quiet hours', 'alerts', 'matrix', 'telegram'] },
  { id: 'automation', label: 'Automation', icon: 'flow', group: 'Keeping it healthy', keywords: ['rules', 'schedule', 'webhook', 'standing approval'] },
  { id: 'about', label: 'About & diagnostics', icon: 'info', group: 'About', keywords: ['version', 'logs', 'diagnostic bundle', 'rescue', 'support'] },
];

export interface SettingsLayoutProps {
  current: SettingsSectionId;
  /** False when the route named no section: phones then show the index list only. */
  explicit: boolean;
  hrefFor: (id: SettingsSectionId) => string;
  /** Link back to the section list (phones). */
  indexHref: string;
  /** Optional status per section, e.g. backups "Verify soon"; always a word, never only a dot. */
  hints?: Partial<Record<SettingsSectionId, { tone: Tone; label: string }>>;
  children: ReactNode;
}

export function SettingsLayout({ current, explicit, hrefFor, indexHref, hints = {}, children }: SettingsLayoutProps) {
  const [q, setQ] = useState('');
  const searchId = useId();
  const shown = SETTINGS_SECTIONS.filter((s) => matchSection(s, q));
  const groups = [...new Set(shown.map((s) => s.group))];
  return (
    <>
      <PageHeader title="Settings" lede="Everything here is also an API call. Changes that add power are requests you approve; changes that take power away happen at once." />
      <div className={cx('om-set', explicit ? 'om-set-in-section' : 'om-set-at-index')}>
        <nav className="om-set-nav" aria-label="Settings sections">
          <label className="om-set-search" htmlFor={searchId}>
            <SetIcon name="search" size={18} />
            <span className="om-visually-hidden">Search settings</span>
            <input id={searchId} type="search" placeholder="Search settings" value={q} onChange={(e) => setQ(e.target.value)} autoComplete="off" />
          </label>
          {shown.length === 0 && (
            <p className="om-hint om-set-nomatch" role="status">
              No setting matches “{q}”.
            </p>
          )}
          {groups.map((g) => (
            <div key={g} className="om-set-nav-group">
              <p className="om-set-nav-title">{g}</p>
              <ul>
                {shown
                  .filter((s) => s.group === g)
                  .map((s) => (
                    <li key={s.id}>
                      <a className="om-set-nav-link" href={hrefFor(s.id)} aria-current={s.id === current && explicit ? 'page' : s.id === current ? 'true' : undefined}>
                        <span className="om-set-nav-icon" aria-hidden="true">
                          <SetIcon name={s.icon} size={18} />
                        </span>
                        <span className="om-set-nav-label">{s.label}</span>
                        {hints[s.id] && <StatusPill tone={hints[s.id]!.tone} label={hints[s.id]!.label} className="om-set-nav-hint" />}
                        <span className="om-set-nav-chev" aria-hidden="true">
                          <SetIcon name="chevron" size={16} />
                        </span>
                      </a>
                    </li>
                  ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="om-set-content" key={current}>
          <a className="om-set-back" href={indexHref}>
            <SetIcon name="back" size={18} /> All settings
          </a>
          {children}
        </div>
      </div>
    </>
  );
}
