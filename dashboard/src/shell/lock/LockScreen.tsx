// SPDX-License-Identifier: Apache-2.0
// The lock screen (design-v2 final screen 11, Atlas): the Contour wallpaper, the box's name, a big clock and
// date, a card that welcomes the person back, how many decisions wait, and where this sign-in goes. Unlocking
// offers every D-034 way in (passkey, password with an optional authenticator code, or an access token):
// passkeys are optional. Nothing here is fetched: the workspace is locked and its credential is gone, so the
// screen shows only the snapshot taken at lock time (state.ts).
import { useEffect, useRef, useState } from 'react';
import { BrandMark, Button, WallpaperSurface, wallpaperLayers } from '@onemind/ui';
import { formatDate, t } from '../../i18n';
import { SignIn } from '../../pages/SignIn';
import type { LockSummary } from './state';

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return parts.slice(0, 2).map((p) => Array.from(p)[0]!.toUpperCase()).join('');
}

/** How this page reaches the box, said plainly: only what the browser itself can vouch for. */
export function whereLine(boxName: string, loc: Pick<Location, 'protocol' | 'hostname'> = window.location): string {
  const local = loc.hostname === '127.0.0.1' || loc.hostname === 'localhost' || loc.hostname === '::1' || loc.hostname === '[::1]';
  const how = local ? t('lock.where.local') : loc.protocol === 'https:' ? t('lock.where.encrypted') : t('lock.where.plain');
  return t('lock.where', { name: boxName, how });
}

export function LockScreen({ summary, mock }: { summary: LockSummary; mock: boolean }) {
  const [view, setView] = useState<'locked' | 'unlock' | 'switch'>('locked');
  const [now, setNow] = useState(() => Date.now());
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (view !== 'locked') return;
    title.current?.focus();
    const timer = window.setInterval(() => setNow(Date.now()), 15_000);
    return () => window.clearInterval(timer);
  }, [view]);

  if (view !== 'locked') return <SignIn mock={mock} lockedBox={summary.boxName} onReturnToLock={() => setView('locked')} switchPerson={view === 'switch'} />;
  const layers = wallpaperLayers('contour', null);
  const when = new Date(now);
  return (
    <main className="dash-signin dash-lock">
      {layers && <WallpaperSurface layers={layers} className="dash-signin-wp dash-lock-wp" />}
      <p className="dash-lock-box"><BrandMark className="om-brand-mark dash-lock-mark" />{summary.boxName}</p>
      <div className="dash-lock-time">
        <time dateTime={when.toISOString()}>{formatDate(when, { timeStyle: 'short' })}</time>
        <p>{formatDate(when, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      </div>
      <div className="dash-signin-card dash-lock-card">
        {summary.person && <span className="dash-lock-avatar" aria-hidden="true">{initials(summary.person)}</span>}
        <h1 ref={title} tabIndex={-1}>
          {summary.person ? t('lock.welcome', { name: summary.person }) : t('lock.title', { name: summary.boxName })}
        </h1>
        <p className="om-hint">{summary.person ? t('lock.lockedBox', { name: summary.boxName }) : t('lock.ways')}</p>
        <Button variant="primary" onClick={() => setView('unlock')}>{t('lock.unlock')}</Button>
        {summary.person && <p className="om-hint dash-lock-ways">{t('lock.ways')}</p>}
        <Button variant="ghost" onClick={() => setView('switch')}>{t('lock.switchPerson')}</Button>
      </div>
      <p className="dash-lock-glance">
        <span className={summary.waiting ? 'dash-lock-dot dash-lock-dot-needs' : 'dash-lock-dot'} aria-hidden="true" />
        {t(summary.waiting === 1 ? 'lock.waiting.one' : 'lock.waiting', { n: summary.waiting })}
      </p>
      <p className="dash-lock-where">{whereLine(summary.boxName)}</p>
    </main>
  );
}
