// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: theme and layout are saved per person in this browser and change nothing on the box;
// the owner also gets the switch for the box's own screen (KioskCard).
import { AppearanceSettings, PageHeader } from '@onemind/ui';
import { KioskCard } from './KioskCard';
import { LanguagePicker } from './LanguagePicker';

export function SettingsAppearance() {
  return (
    <>
      <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout are saved for you only and change nothing on the box. The owner also chooses what the box's own screen shows." />
      <AppearanceSettings />
      <LanguagePicker />
      <KioskCard />
    </>
  );
}
