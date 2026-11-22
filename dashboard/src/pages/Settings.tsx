// SPDX-License-Identifier: Apache-2.0
// Settings on @onemind/ui SettingsLayout. Each sub-page declares itself in src/screens/settings-pages/<id>.ts
// (a page this hub serves, or the work stream whose API brings it); this file only looks it up.
// Appearance is live (saved per person in this browser until the §12 preferences route lands).
// A section without a page says which work stream brings its API, instead of showing controls
// that would do nothing.
import { lazy, Suspense, useMemo } from 'react';
import { useParams } from 'react-router';
import { EmptyState, SETTINGS_SECTIONS, SettingsLayout, StateView, type SettingsSectionId } from '@onemind/ui';
import { SETTINGS_PAGES } from '../screens/registry';
import { href } from '../shell/routes';

const IDS = new Set(SETTINGS_SECTIONS.map((s) => s.id));

export function Settings() {
  const { section } = useParams();
  const explicit = !!section && IDS.has(section as SettingsSectionId);
  const current = (explicit ? section : 'appearance') as SettingsSectionId;
  const meta = SETTINGS_SECTIONS.find((s) => s.id === current)!;
  const page = SETTINGS_PAGES.get(current);
  const Page = useMemo(() => (page?.load ? lazy(page.load) : null), [page]);
  let body;
  if (Page) body = <Suspense fallback={<StateView state="loading" what={meta.label} skeleton="list" />}><Page /></Suspense>;
  else {
    const c = page?.coming ?? { stream: 'its work stream', api: null };
    body = (
      <EmptyState icon="settings" title={`${meta.label}: coming with ${c.stream}`} command={c.api ? `GET ${c.api.split(',')[0]!.trim()}` : undefined}>
        <p>
          Coming soon. This hub does not serve these settings yet. They arrive with the {c.stream} work stream ({c.api ? `${c.api}, contract §12` : 'its API is not in contract §12 yet'}). Nothing here is a placeholder control that would do
          nothing.
        </p>
      </EmptyState>
    );
  }
  return (
    <SettingsLayout current={current} explicit={explicit} hrefFor={(id) => href.setting(id)} indexHref={href.settings}>
      {body}
    </SettingsLayout>
  );
}
