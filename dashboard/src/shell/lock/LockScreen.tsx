// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from 'react';
import { Button, WallpaperSurface, wallpaperLayers } from '@onemind/ui';
import { SignIn } from '../../pages/SignIn';
import type { LockSummary } from './state';

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
  return (
    <main className="dash-signin">
      {layers && <WallpaperSurface layers={layers} className="dash-signin-wp" />}
      <div className="dash-signin-card">
        <h1 ref={title} tabIndex={-1}>{summary.boxName} is locked</h1>
        <time dateTime={new Date(now).toISOString()}>{new Intl.DateTimeFormat(undefined, { timeStyle: 'short' }).format(now)}</time>
        <p>{summary.waiting} waiting for a decision</p>
        <Button variant="primary" onClick={() => setView('unlock')}>Unlock</Button>
        <Button variant="ghost" onClick={() => setView('switch')}>Switch person</Button>
      </div>
    </main>
  );
}
