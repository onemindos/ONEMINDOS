// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: theme, layout and the idle lock are saved per person in this browser and change nothing on the box;
// the owner also gets the switch for the box's own screen (KioskCard).
import { useState } from 'react';
import { AppearanceSettings, PageHeader } from '@onemind/ui';
import { KioskCard } from './KioskCard';
import { LanguagePicker } from './LanguagePicker';
import { useSignedIn } from '../session';
import { idleOptions, inKiosk, saveIdleLock, useIdleLockPreference, type IdleMinutes } from '../shell/lock/state';

export function SettingsAppearance() {
  const { account, principal } = useSignedIn();
  const identity = account ?? principal;
  const person = identity?.kind === 'person' ? identity.id : undefined;
  const idle = useIdleLockPreference(person, identity?.role === 'owner');
  const [lockSaveError, setLockSaveError] = useState(false);
  return (
    <>
      <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout are saved for you only and change nothing on the box. The owner also chooses what the box's own screen shows." />
      <AppearanceSettings />
      <LanguagePicker />
      {person && <section>
        <label htmlFor="idle-lock">Lock the desktop after</label>
        <select id="idle-lock" value={idle} onChange={(event) => setLockSaveError(!saveIdleLock(person, Number(event.target.value) as IdleMinutes))}>
          {idleOptions.filter((minutes) => minutes || !inKiosk()).map((minutes) => <option key={minutes} value={minutes}>{minutes ? `${minutes} minutes` : 'Off'}</option>)}
        </select>
        {lockSaveError && <p role="alert">Could not save the lock preference in this browser.</p>}
      </section>}
      <KioskCard />
    </>
  );
}
