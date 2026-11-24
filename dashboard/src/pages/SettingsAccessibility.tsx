// SPDX-License-Identifier: Apache-2.0
import { Card, PageHeader, useCustomize } from '@onemind/ui';

const motionOptions = [
  { value: 'system', label: 'Follow system' },
  { value: 'reduce', label: 'Reduce motion' },
  { value: 'full', label: 'Full motion' },
] as const;
const sizes = [{ value: 1, label: 'Standard' }, { value: 1.125, label: 'Large' }, { value: 1.25, label: 'Extra large' }] as const;

export function SettingsAccessibility() {
  const { prefs, update } = useCustomize();
  return <>
    <PageHeader title="Accessibility and motion" />
    <Card title="Reading and movement">
      <fieldset>
        <legend>Motion</legend>
        {motionOptions.map(({ value, label }) => <label key={value}>
          <input type="radio" name="motion-mode" checked={prefs.motion === value} onChange={() => update({ motion: value })} /> {label}
        </label>)}
      </fieldset>
      <fieldset>
        <legend>Text size</legend>
        {sizes.map(({ value, label }) => <label key={value}>
          <input type="radio" name="reading-size" checked={prefs.fontScale === value || value === 1 && prefs.fontScale < 1}
            onChange={() => update({ fontScale: value })} /> {label}
        </label>)}
      </fieldset>
      <div className="dash-stack">
        <label><input type="checkbox" checked={prefs.higherContrast} onChange={(event) => update({ higherContrast: event.target.checked })} /> Higher contrast</label>
        <label><input type="checkbox" checked={prefs.focusAlways} onChange={(event) => update({ focusAlways: event.target.checked })} /> Always show focus rings</label>
        <label><input type="checkbox" checked={prefs.underlineLinks} onChange={(event) => update({ underlineLinks: event.target.checked })} /> Underline links</label>
      </div>
    </Card>
    <Card title="Preview">
      <p>This text uses your current reading preferences.</p>
      <a href="/settings/appearance">Appearance settings</a>
    </Card>
  </>;
}
