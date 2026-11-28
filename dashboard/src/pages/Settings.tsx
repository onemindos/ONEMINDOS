// SPDX-License-Identifier: Apache-2.0
// Settings on @onemind/ui SettingsLayout. Each sub-page declares itself in src/screens/settings-pages/<id>.ts
// (a page this hub serves, or the work stream whose API brings it); this file only looks it up.
// Appearance is live (saved per person in this browser until the §12 preferences route lands).
// All 21 sections have a page or a screen of their own; a missing one gets a plain not-found state.
import { lazy, Suspense, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router';
import { EmptyState, SETTINGS_SECTIONS, SettingsLayout, StateView, type SettingsSectionId } from '@onemind/ui';
import { SETTINGS_PAGES } from '../screens/registry';
import { href } from '../shell/routes';
import { ProOnly } from '../shell/ProOnly';
import { useShell } from '../shell/Shell';
import { PRO_SETTINGS } from '../shell/proSettings';
import { useTipSearch } from '../data/useTipSearch';

const IDS = new Set(SETTINGS_SECTIONS.map((s) => s.id));

export function Settings() {
  const { section } = useParams();
  const { view, role } = useShell();
  const [query, setQuery] = useState('');
  const tips = useTipSearch(query);
  const explicit = !!section && IDS.has(section as SettingsSectionId);
  const current = (explicit ? section : 'appearance') as SettingsSectionId;
  const meta = SETTINGS_SECTIONS.find((s) => s.id === current)!;
  const page = SETTINGS_PAGES.get(current);
  const Page = useMemo(() => (page?.load ? lazy(page.load) : null), [page]);
  let body;
  if (view !== 'pro' && PRO_SETTINGS.has(current)) body = <ProOnly title={meta.label}>{null}</ProOnly>;
  else if (Page) body = <Suspense fallback={<StateView state="loading" what={meta.label} skeleton="list" />}><Page /></Suspense>;
  else if (page?.to) {
    // These settings live on a screen of their own; the redirect normally sends people there before this renders.
    body = (
      <EmptyState icon="settings" title={`${meta.label} has its own screen`}>
        <p>
          <Link to={page.to}>Open {meta.label}</Link>
        </p>
      </EmptyState>
    );
  } else {
    // Every section has a page or its own screen; this is only the safe answer if a definition goes missing.
    body = (
      <EmptyState icon="settings" title={`${meta.label} is not available`}>
        <p>
          This section could not be found. <Link to={href.settings}>Back to all settings</Link>
        </p>
      </EmptyState>
    );
  }
  const tipResults = tips.length > 0 && (
    <div className="om-set-nav-group">
      <p className="om-set-nav-title">Tips</p>
      <ul>{tips.map(tip => <li key={tip.id}>
        <Link className="om-set-nav-link" to={tip.href} aria-label={`Open ${tip.title}`}>
          <span className="om-set-nav-label">{tip.title}</span> Open
        </Link>
      </li>)}</ul>
    </div>
  );
  return (
    <>
      <SettingsLayout current={current} explicit={explicit} hrefFor={(id) => href.setting(id)} indexHref={href.settings} hidden={view !== 'pro' ? PRO_SETTINGS : role === 'owner' ? undefined : new Set<SettingsSectionId>(['care'])}
        onSearch={setQuery} extraSearchResults={tipResults}>
        {body}
      </SettingsLayout>
      <p className="om-visually-hidden" role="status" aria-label="Tips search">
        {tips.length > 0 && `${tips.length} ${tips.length === 1 ? 'tip' : 'tips'} found.`}
      </p>
    </>
  );
}
