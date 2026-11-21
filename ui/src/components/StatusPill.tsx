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
  /** "We do not know": a dashed ring with a question mark, so it differs from the hollow Offline ring by shape. */
  unknown?: boolean;
  className?: string;
}

/**
 * One glyph per tone, so colour is never the only signal (WCAG 1.4.1): a check for ok, a triangle
 * for warn, an octagon with an x for bad, a question mark in a dashed ring for unknown, a hollow
 * ring for neutral (offline, expired), a filled dot for info and agent.
 */
function Glyph({ tone, unknown }: { tone: Tone; unknown: boolean }) {
  const p = { viewBox: '0 0 14 14', width: 14, height: 14, fill: 'none', stroke: 'currentColor', strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true, focusable: false } as const;
  if (unknown)
    return (
      <svg {...p} data-glyph="unknown">
        <circle cx="7" cy="7" r="5.6" strokeWidth="1.3" strokeDasharray="2.2 1.8" />
        <path d="M5.5 5.6a1.6 1.6 0 1 1 2.3 1.4c-.5.3-.8.6-.8 1.2M7 10v.1" strokeWidth="1.4" />
      </svg>
    );
  if (tone === 'ok')
    return (
      <svg {...p} data-glyph="ok">
        <path d="M2.6 7.4l2.9 2.9 5.9-6.2" strokeWidth="2" />
      </svg>
    );
  if (tone === 'warn')
    return (
      <svg {...p} data-glyph="warn">
        <path d="M7 1.8L13 12H1z" />
        <path d="M7 5.6v3M7 10.4v.1" />
      </svg>
    );
  if (tone === 'bad')
    return (
      <svg {...p} data-glyph="bad">
        <path d="M4.6 1.4h4.8l3.2 3.2v4.8l-3.2 3.2H4.6L1.4 9.4V4.6z" />
        <path d="M5 5l4 4M9 5l-4 4" />
      </svg>
    );
  if (tone === 'neutral')
    return (
      <svg {...p} data-glyph="neutral">
        <circle cx="7" cy="7" r="4.4" />
      </svg>
    );
  return (
    <svg {...p} data-glyph={tone}>
      <circle cx="7" cy="7" r="3.4" fill="currentColor" stroke="none" />
    </svg>
  );
}

export function StatusPill({ tone, label, detail, pulse = false, dot = true, unknown = false, className }: StatusPillProps) {
  return (
    <span className={cx('om-pill', `om-tone-${tone}`, className)}>
      {dot && <span className={cx('om-pill-dot', pulse && 'om-pulse')} aria-hidden="true">
          <Glyph tone={tone} unknown={unknown} />
        </span>}
      <span className="om-pill-label">{label}</span>
      {detail && <span className="om-pill-detail">· {detail}</span>}
    </span>
  );
}

/** The freshness rule as a pill: Online / Stale / Offline / Unknown. */
export function FreshnessPill({ state, detail }: { state: Freshness; detail?: string }) {
  return <StatusPill tone={FRESHNESS_TONE[state]} label={FRESHNESS_LABEL[state]} detail={detail} unknown={state === 'unknown'} pulse={state === 'live'} />;
}
