// SPDX-License-Identifier: Apache-2.0
import type { Tone } from '../tokens/tokens';

/**
 * The small mark in front of a status: every tone has its own shape, so a state is never told
 * apart by colour alone (WCAG 1.4.1; deutan and protan vision cannot separate green from red).
 *   ok       filled dot with a check          warn    ring with clock hands (attention, waiting)
 *   bad      filled triangle with a bar       neutral dashed ring with "?" (unknown, offline)
 *   info     filled dot                       agent   filled diamond
 * The glyph takes its colour from --om-tone-fg and cuts its detail out in --om-tone-bg.
 */
export function ToneGlyph({ tone, size = 10 }: { tone: Tone; size?: number }) {
  const cut = 'var(--om-tone-bg, var(--om-color-surface))';
  const common = { width: size, height: size, viewBox: '0 0 12 12', 'aria-hidden': true, focusable: false, className: 'om-tone-glyph' } as const;
  switch (tone) {
    case 'ok':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="6" fill="currentColor" />
          <path d="M3.4 6.2l1.8 1.8 3.4-3.7" fill="none" stroke={cut} strokeWidth="1.6" strokeLinecap="square" strokeLinejoin="miter" />
        </svg>
      );
    case 'warn':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.5" />
          <path d="M6 3.2V6l1.9 1.2" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="square" />
        </svg>
      );
    case 'bad':
      return (
        <svg {...common}>
          <path d="M6 .6L11.8 11H.2z" fill="currentColor" />
          <path d="M6 4.4v3.2M6 8.9v.4" stroke={cut} strokeWidth="1.5" strokeLinecap="square" />
        </svg>
      );
    case 'neutral':
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="5" fill="none" stroke="currentColor" strokeWidth="1.3" strokeDasharray="2 1.6" />
          <path d="M4.7 4.8a1.4 1.4 0 112 1.2c-.5.3-.7.6-.7 1.1M6 8.6v.3" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="square" />
        </svg>
      );
    case 'agent':
      return (
        <svg {...common}>
          <path d="M6 .4L11.6 6 6 11.6.4 6z" fill="currentColor" />
        </svg>
      );
    default:
      return (
        <svg {...common}>
          <circle cx="6" cy="6" r="4.5" fill="currentColor" />
        </svg>
      );
  }
}
