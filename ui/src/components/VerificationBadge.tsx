// SPDX-License-Identifier: Apache-2.0
// How strongly a person is checked (D-028, amended by D-034). A badge names the level
// and describes the supported proof without assuming how a passkey verified the person.
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
  L1: 'A passkey that verified you, or a fresh password and authenticator code.',
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
  const meaning = required && level === 'L2'
    ? 'A proven key, or for eligible local changes, an L1 check and the code on the box’s screen.' : LEVEL_MEANING[level];
  return (
    <span className={cx('om-pill', `om-tone-${TONE[level]}`, 'om-verify', className)} data-level={level}
      title={meaning}>
      <span className="om-verify-mark" aria-hidden="true">{levelRank(level) ? '●'.repeat(levelRank(level)) : '○'}</span>
      <span className="om-pill-label">{text}</span>
      <span className="om-visually-hidden">. {meaning}</span>
    </span>
  );
}
