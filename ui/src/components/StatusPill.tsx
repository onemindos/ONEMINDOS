// SPDX-License-Identifier: Apache-2.0
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';
import { StatusGlyph, type GlyphKind } from './StatusGlyph';
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
  /** A shaped glyph instead of the dot, for states whose meaning must not rest on colour or on a plain dot. */
  glyph?: GlyphKind;
  className?: string;
}

/** A pill is never silent: with no wording given it says what its tone means. */
export const TONE_WORD: Record<Tone, string> = { ok: 'Done', warn: 'Check', bad: 'Problem', info: 'Info', neutral: 'Noted', agent: 'AI agent' };

export function StatusPill({ tone, label, detail, pulse = false, dot = true, glyph, className }: StatusPillProps) {
  const word = label.trim() || TONE_WORD[tone];
  return (
    <span className={cx('om-pill', `om-tone-${tone}`, className)}>
      {glyph ? <StatusGlyph kind={glyph} size={14} className="om-pill-glyph" /> : dot && <span className={cx('om-pill-dot', pulse && 'om-pulse')} aria-hidden="true" />}
      <span className="om-pill-label">{word}</span>
      {detail && <span className="om-pill-detail">· {detail}</span>}
    </span>
  );
}

/** Each freshness state has its own shape: unknown is a dashed ring with "?", never a check. */
export const FRESHNESS_GLYPH: Record<Freshness, GlyphKind> = { live: 'ok', stale: 'warn', offline: 'neutral', unknown: 'unknown' };

/** The freshness rule as a pill: Online / Stale / Offline / Unknown. */
export function FreshnessPill({ state, detail }: { state: Freshness; detail?: string }) {
  return <StatusPill tone={FRESHNESS_TONE[state]} label={FRESHNESS_LABEL[state]} detail={detail} glyph={FRESHNESS_GLYPH[state]} />;
}
