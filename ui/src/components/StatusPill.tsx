// SPDX-License-Identifier: Apache-2.0
import type { Tone } from '../tokens/tokens';
import { ToneGlyph } from './ToneGlyph';
import { cx } from '../lib/cx';
import { FRESHNESS_LABEL, FRESHNESS_TONE, type Freshness } from '../lib/freshness';

export interface StatusPillProps {
  tone: Tone;
  /** Always a word: colour is never the only signal (WCAG 1.4.1). */
  label: string;
  /** Extra text after the label, e.g. "last seen 4 min ago". */
  detail?: string;
  /** Pulsing dot for something in progress; static dot otherwise. */
  pulse?: boolean;
  dot?: boolean;
  /** Required when `label` is empty (a dot-only pill): a pill never says nothing. */
  ariaLabel?: string;
  className?: string;
}

export function StatusPill({ tone, label, detail, pulse = false, dot = true, ariaLabel, className }: StatusPillProps) {
  const text = label.trim();
  // An empty pill is a coloured blob that screen readers skip: render nothing instead.
  if (!text && !ariaLabel) return null;
  return (
    <span className={cx('om-pill', `om-tone-${tone}`, className)} aria-label={text ? undefined : ariaLabel} role={text ? undefined : 'img'}>
      {dot && (
        <span className={cx('om-pill-dot', pulse && 'om-pulse')} aria-hidden="true">
          <ToneGlyph tone={tone} />
        </span>
      )}
      {text && <span className="om-pill-label">{label}</span>}
      {detail && <span className="om-pill-detail">· {detail}</span>}
    </span>
  );
}

/** The freshness rule as a pill: Online / Stale / Offline / Unknown. */
export function FreshnessPill({ state, detail }: { state: Freshness; detail?: string }) {
  return <StatusPill tone={FRESHNESS_TONE[state]} label={FRESHNESS_LABEL[state]} detail={detail} />;
}
