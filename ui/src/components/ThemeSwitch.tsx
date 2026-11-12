// SPDX-License-Identifier: Apache-2.0
import { useState } from 'react';
import { applyTheme, storedTheme, type ThemeChoice } from '../lib/theme';

const OPTIONS: Array<[ThemeChoice, string]> = [
  ['system', 'System'],
  ['light', 'Light'],
  ['dark', 'Dark'],
];

/** Segmented radio group: System / Light / Dark. */
export function ThemeSwitch({ initial }: { initial?: ThemeChoice }) {
  const [choice, setChoice] = useState<ThemeChoice>(() => initial ?? storedTheme());
  return (
    <fieldset className="om-segmented">
      <legend className="om-visually-hidden">Colour theme</legend>
      {OPTIONS.map(([value, label]) => (
        <label key={value} className={choice === value ? 'om-seg-on' : undefined}>
          <input
            type="radio"
            name="om-theme"
            value={value}
            checked={choice === value}
            onChange={() => {
              setChoice(value);
              applyTheme(value);
            }}
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
