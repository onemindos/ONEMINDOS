// SPDX-License-Identifier: Apache-2.0
import type { Tone } from '../tokens/tokens';
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
  className?: string;
}

export function StatusPill({ tone, label, detail, pulse = false, dot = true, className }: StatusPillProps) {
  return (
    <span className={cx('om-pill', `om-tone-${tone}`, className)}>
      {dot && <span className={cx('om-pill-dot', pulse && 'om-pulse')} aria-hidden="true" />}
      <span className="om-pill-label">{label}</span>
      {detail && <span className="om-pill-detail">· {detail}</span>}
    </span>
  );
}

/** The freshness rule as a pill: Online / Stale / Offline / Unknown. */
export function FreshnessPill({ state, detail }: { state: Freshness; detail?: string }) {
  return <StatusPill tone={FRESHNESS_TONE[state]} label={FRESHNESS_LABEL[state]} detail={detail} />;
}
