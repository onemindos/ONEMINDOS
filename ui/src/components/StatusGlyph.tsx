// SPDX-License-Identifier: Apache-2.0
// One small shape per meaning, so state is never carried by colour alone (WCAG 1.4.1) and two
// different states never share an outline: ok = check, warn = triangle, bad = cross,
// info = "i", neutral/offline = dash, unknown = dashed ring with "?", progress = open arc.
// Unknown is never shaped like ok, and stale (triangle) is never shaped like offline (dash).
import type { ReactNode } from 'react';
import type { Tone } from '../tokens/tokens';
import { cx } from '../lib/cx';

export type GlyphKind = Tone | 'unknown' | 'progress';

const SHAPES: Record<GlyphKind, ReactNode> = {
  ok: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12.5l2.7 2.7L16 9.5" />
    </>
  ),
  warn: <path d="M12 4l9 16H3zM12 10v4M12 17h.01" />,
  bad: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6M15 9l-6 6" />
    </>
  ),
  info: <path d="M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5h.01" />,
  agent: <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />,
  neutral: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h8" />
    </>
  ),
  unknown: (
    <>
      <circle cx="12" cy="12" r="9" strokeDasharray="3 3" />
      <path d="M9.6 9.6a2.4 2.4 0 1 1 3.4 2.2c-.7.4-1 .9-1 1.7M12 16.8h.01" />
    </>
  ),
  progress: (
    <>
      <circle cx="12" cy="12" r="9" opacity="0.3" />
      <path d="M12 3a9 9 0 0 1 9 9" strokeWidth="2.6" />
    </>
  ),
};

export interface StatusGlyphProps {
  kind: GlyphKind;
  /** 14 to 16 px in list rows. */
  size?: number;
  /** Spin the progress arc. Stops under prefers-reduced-motion. */
  spin?: boolean;
  className?: string;
}

/** Decorative: the state is always also written as a word next to it. */
export function StatusGlyph({ kind, size = 16, spin = false, className }: StatusGlyphProps) {
  const tone: Tone = kind === 'unknown' ? 'neutral' : kind === 'progress' ? 'info' : kind;
  return (
    <svg
      className={cx('om-glyph', `om-tone-${tone}`, `om-glyph-${kind}`, spin && kind === 'progress' && 'om-glyph-spin', className)}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {SHAPES[kind]}
    </svg>
  );
}
