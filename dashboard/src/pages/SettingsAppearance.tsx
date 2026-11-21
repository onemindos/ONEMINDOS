// SPDX-License-Identifier: Apache-2.0
// Settings > Appearance: saved per person in this browser; it changes nothing on the box.
import { AppearanceSettings, PageHeader } from '@onemind/ui';

export function SettingsAppearance() {
  return (
    <>
      <PageHeader title="Appearance" lede="Theme, accent, wallpaper and layout. Saved for you only; it changes nothing on the box, so it needs no approval." />
      <AppearanceSettings />
    </>
  );
}
