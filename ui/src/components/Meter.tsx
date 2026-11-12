// SPDX-License-Identifier: Apache-2.0
import { cx } from '../lib/cx';

export interface MeterProps {
  label: string;
  /** 0..max */
  value: number;
  max: number;
  /** Human text, e.g. "5.1 of 7.8 GB used". */
  valueText: string;
  /** Fraction at which the bar turns warn / bad. */
  warnAt?: number;
  badAt?: number;
  /** Dim the bar: the value is a last report, not live. */
  stale?: boolean;
}

export function Meter({ label, value, max, valueText, warnAt = 0.8, badAt = 0.92, stale }: MeterProps) {
  const f = max > 0 ? Math.min(1, Math.max(0, value / max)) : 0;
  const tone = f >= badAt ? 'bad' : f >= warnAt ? 'warn' : 'ok';
  return (
    <div className={cx('om-meter', stale && 'om-meter-stale')}>
      <div className="om-meter-row">
        <span className="om-meter-label">{label}</span>
        <span className="om-meter-value">{valueText}</span>
      </div>
      <div
        className={cx('om-meter-track', `om-tone-${tone}`)}
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        aria-valuetext={valueText}
      >
        <span className="om-meter-fill" style={{ width: `${(f * 100).toFixed(1)}%` }} />
      </div>
    </div>
  );
}
