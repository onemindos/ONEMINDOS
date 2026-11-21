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
  /** Shape override: 'unknown' draws a dashed ring with a question mark. */
  glyph?: PillGlyph;
  className?: string;
}

export type PillGlyph = 'check' | 'clock' | 'x' | 'info' | 'ring' | 'unknown' | 'agent';

/** Every tone has its own shape, so status is never colour alone (WCAG 1.4.1). */
const TONE_GLYPH: Record<Tone, PillGlyph> = { ok: 'check', warn: 'clock', bad: 'x', info: 'info', neutral: 'ring', agent: 'agent' };

/** A 12 px status shape: check, clock, x, i, hollow ring, dashed ring with ?, spark. */
export function PillGlyphMark({ glyph, pulse = false }: { glyph: PillGlyph; pulse?: boolean }) {
  const common = { fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round', strokeLinejoin: 'round' } as const;
  return (
    <svg className={cx('om-pill-glyph', pulse && 'om-pulse')} data-glyph={glyph} viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
      {glyph === 'check' && <path {...common} d="M3 8.5l3.2 3.2L13 4.8" />}
      {glyph === 'clock' && (
        <>
          <circle {...common} cx="8" cy="8" r="6" />
          <path {...common} d="M8 4.8V8l2.2 1.4" />
        </>
      )}
      {glyph === 'x' && <path {...common} d="M4 4l8 8M12 4l-8 8" />}
      {glyph === 'info' && <path {...common} d="M8 7.2v4.3M8 4.6h.01" />}
      {glyph === 'ring' && <circle {...common} cx="8" cy="8" r="5" />}
      {glyph === 'unknown' && (
        <>
          <circle {...common} cx="8" cy="8" r="6" strokeDasharray="2.2 2.2" strokeWidth={1.5} />
          <path {...common} strokeWidth={1.6} d="M6.5 6.5a1.6 1.6 0 1 1 2.3 1.4c-.6.3-.8.7-.8 1.2M8 11.4h.01" />
        </>
      )}
      {glyph === 'agent' && <path {...common} d="M8 2.5l1.3 3.7L13 7.5 9.3 8.8 8 12.5 6.7 8.8 3 7.5l3.7-1.3z" />}
    </svg>
  );
}

export function StatusPill({ tone, label, detail, pulse = false, dot = true, glyph, className }: StatusPillProps) {
  return (
    <span className={cx('om-pill', `om-tone-${tone}`, className)} data-state={glyph === 'unknown' ? 'unknown' : undefined}>
      {dot && <PillGlyphMark glyph={glyph ?? TONE_GLYPH[tone]} pulse={pulse} />}
      <span className="om-pill-label">{label}</span>
      {detail && <span className="om-pill-detail">· {detail}</span>}
    </span>
  );
}

/** The freshness rule as a pill: Online / Stale / Offline / Unknown. */
export function FreshnessPill({ state, detail }: { state: Freshness; detail?: string }) {
  return <StatusPill tone={FRESHNESS_TONE[state]} label={FRESHNESS_LABEL[state]} detail={detail} glyph={state === 'unknown' ? 'unknown' : undefined} />;
}
