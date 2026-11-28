// SPDX-License-Identifier: Apache-2.0
// How strongly a person is checked (D-028; gateway permissions design 3.11). The badge names the
// level and what OneMind proved about the key, never the method: WebAuthn tells the box "the person
// was verified on the device", not whether that was a face, a fingerprint or a PIN, so the words
// here never claim one. Colour is never the only signal: every level is a word and an L-number.
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';

export type VerificationLevel = 'L0' | 'L1' | 'L2' | 'L3';

export const LEVEL_NAME: Record<VerificationLevel, string> = {
  L0: 'Signed in',
  L1: 'Device check',
  L2: 'Proven key',
  L3: 'Biometric-only key',
};

/** What each level proves, in words that make no claim about which check the device used. */
export const LEVEL_MEANING: Record<VerificationLevel, string> = {
  L0: 'A live sign-in, nothing more.',
  L1: 'Your device checked you before using this key. OneMind can’t tell how.',
  L2: 'A key whose make and model OneMind could prove, that never leaves its device.',
  L3: 'A proven key that the hardware unlocks only after its own biometric check.',
};

const TONE: Record<VerificationLevel, Tone> = { L0: 'neutral', L1: 'info', L2: 'ok', L3: 'ok' };

export const levelRank = (l: VerificationLevel): number => Number(l.slice(1));

export interface VerificationBadgeProps {
  level: VerificationLevel;
  /** "Needs L2 · Proven key" for a requirement; the plain level for a key. */
  required?: boolean;
  className?: string;
}

export function VerificationBadge({ level, required = false, className }: VerificationBadgeProps) {
  const text = `${required ? 'Needs ' : ''}${level} · ${LEVEL_NAME[level]}`;
  return (
    <span className={cx('om-pill', `om-tone-${TONE[level]}`, 'om-verify', className)} data-level={level}
      title={LEVEL_MEANING[level]}>
      <span className="om-verify-mark" aria-hidden="true">{levelRank(level) ? '●'.repeat(levelRank(level)) : '○'}</span>
      <span className="om-pill-label">{text}</span>
      <span className="om-visually-hidden">. {LEVEL_MEANING[level]}</span>
    </span>
  );
}
