// SPDX-License-Identifier: Apache-2.0
// Small form controls for the Appearance screen. Built on native radios and ranges, so arrow
// keys, Tab order and screen-reader announcements come from the browser. Candidates for the
// library's planned Input / Switch / Form field set (COMPONENTS.md).
import { useId, type ReactNode } from 'react';
import { cx } from '../lib/cx';

export interface Choice<T extends string | number> {
  value: T;
  label: string;
  /** Optional visual above or beside the label (decorative). */
  visual?: ReactNode;
  hint?: string;
}

export interface ChoiceGroupProps<T extends string | number> {
  legend: string;
  /** Show the legend visually (default) or only to screen readers. */
  hideLegend?: boolean;
  description?: ReactNode;
  value: T;
  choices: Array<Choice<T>>;
  onChange: (v: T) => void;
  /** `segmented`: one row of pills; `cards`: tiles with a visual. */
  variant?: 'segmented' | 'cards';
  disabled?: boolean;
  className?: string;
}

/** A radio group drawn as segmented pills or visual cards. */
export function ChoiceGroup<T extends string | number>({
  legend,
  hideLegend,
  description,
  value,
  choices,
  onChange,
  variant = 'segmented',
  disabled,
  className,
}: ChoiceGroupProps<T>) {
  const name = useId();
  const descId = `${name}-d`;
  return (
    <fieldset className={cx('om-cz-group', className)} aria-describedby={description ? descId : undefined} disabled={disabled}>
      <legend className={hideLegend ? 'om-visually-hidden' : 'om-cz-legend'}>{legend}</legend>
      {description && (
        <p id={descId} className="om-cz-desc">
          {description}
        </p>
      )}
      <div className={variant === 'cards' ? 'om-cz-cards' : 'om-cz-seg'}>
        {choices.map((c) => {
          const on = c.value === value;
          return (
            <label key={String(c.value)} className={cx(variant === 'cards' ? 'om-cz-card' : 'om-cz-seg-item', on && 'om-cz-on')}>
              <input type="radio" name={name} value={String(c.value)} checked={on} onChange={() => onChange(c.value)} />
              {c.visual}
              <span className="om-cz-choice-label">{c.label}</span>
              {c.hint && <span className="om-cz-choice-hint">{c.hint}</span>}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}

export interface RangeFieldProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step?: number;
  onChange: (v: number) => void;
  /** Text for the current value ("12 px", "40 %"); also the aria-valuetext. */
  format: (v: number) => string;
  hint?: ReactNode;
  /** A floor shown on the track (the contrast minimum), in the same units as value. */
  floor?: number;
  disabled?: boolean;
}

export function RangeField({ label, value, min, max, step = 1, onChange, format, hint, floor, disabled }: RangeFieldProps) {
  const id = useId();
  const pct = (v: number) => `${((v - min) / (max - min)) * 100}%`;
  return (
    <div className={cx('om-cz-range', disabled && 'om-cz-disabled')}>
      <div className="om-cz-range-head">
        <label htmlFor={id}>{label}</label>
        <output htmlFor={id} className="om-cz-range-value">
          {format(value)}
        </output>
      </div>
      <div className="om-cz-range-track" style={{ ['--om-cz-fill' as string]: pct(value), ['--om-cz-floor' as string]: floor !== undefined ? pct(floor) : '0%' }}>
        {floor !== undefined && floor > min && <span className="om-cz-range-floor" aria-hidden="true" />}
        <input
          id={id}
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          disabled={disabled}
          aria-valuetext={format(value)}
          aria-describedby={hint ? `${id}-h` : undefined}
          onChange={(e) => onChange(Number(e.target.value))}
        />
      </div>
      {hint && (
        <p id={`${id}-h`} className="om-cz-desc">
          {hint}
        </p>
      )}
    </div>
  );
}

/** One labelled row: text on the left, a control on the right (stacks on phones). */
export function SettingRow({ title, description, children }: { title: string; description?: ReactNode; children: ReactNode }) {
  return (
    <div className="om-cz-row">
      <div className="om-cz-row-text">
        <span className="om-cz-row-title">{title}</span>
        {description && <span className="om-cz-desc">{description}</span>}
      </div>
      <div className="om-cz-row-control">{children}</div>
    </div>
  );
}
