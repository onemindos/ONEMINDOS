// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: saved per person in this browser; it changes nothing on the box.
import { useState } from 'react';
import { AppearanceSettings, PageHeader } from '@onemind/ui';
import { LanguagePicker } from './LanguagePicker';
import { useSignedIn } from '../session';
import { idleOptions, saveIdleLock, useIdleLockPreference, type IdleMinutes } from '../shell/lock/state';

export function SettingsAppearance() {
  const { account, principal } = useSignedIn();
  const identity = account ?? principal;
  const person = identity?.kind === 'person' ? identity.id : undefined;
  const idle = useIdleLockPreference(person, identity?.role === 'owner');
  const [lockSaveError, setLockSaveError] = useState(false);
  return (
    <>
      <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout. Saved for you only; it changes nothing on the box, so it needs no approval." />
      <AppearanceSettings />
      <LanguagePicker />
      {person && <section>
        <label htmlFor="idle-lock">Lock the desktop after</label>
        <select id="idle-lock" value={idle} onChange={(event) => setLockSaveError(!saveIdleLock(person, Number(event.target.value) as IdleMinutes))}>
          {idleOptions.map((minutes) => <option key={minutes} value={minutes}>{minutes ? `${minutes} minutes` : 'Off'}</option>)}
        </select>
        {lockSaveError && <p role="alert">Could not save the lock preference in this browser.</p>}
      </section>}
    </>
  );
}
