// SPDX-License-Identifier: Apache-2.0
// Category icons (docs/design/TAXONOMY.md §1.2): twelve paths drawn for OneMind in the same
// style as ui/src/components/Icon.tsx (24 px grid, 1.75 stroke, round caps, currentColor),
// plus four names that reuse that set. No third-party icon was used or traced.
import { Icon } from '../components/Icon';

const OWN = {
  folder: 'M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z',
  play: 'M4 5h16v14H4zM10 9v6l5-3z',
  note: 'M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h5',
  tasks: 'M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17M11 6h9M11 12h9M11 18h9',
  chat: 'M4 5h16v10H9l-5 4zM8 9h8M8 12h5',
  flow: 'M4 4h6v5H4zM14 15h6v5h-6zM7 9v4h10v2',
  radar: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12l6-6',
  code: 'M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16',
  heart: 'M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z',
  wallet: 'M4 7h15a1 1 0 0 1 1 1v11H4zM4 7l12-3v3M16 13h.01',
  book: 'M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0 0 4h13',
  radio: 'M12 12h.01M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8',
  // Store-only glyphs, same style.
  sparkle: 'M12 3l1.6 4.8L18.5 9.5l-4.9 1.7L12 16l-1.6-4.8L5.5 9.5l4.9-1.7zM18 15l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z',
  grid: 'M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z',
  download: 'M12 4v11M7 10l5 5 5-5M4 19h16',
  copy: 'M9 9h11v11H9zM5 15V4h11',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
  eyeOff: 'M3 3l18 18M10.6 5.1A10 10 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3 3.9M6.6 6.6C3.8 8.4 2 12 2 12s3.5 7 10 7a9.6 9.6 0 0 0 4.4-1M9.9 9.9a3 3 0 0 0 4.2 4.2',
  stop: 'M6 6h12v12H6z',
  restart: 'M4 12a8 8 0 1 0 2.3-5.7M4 4v5h5',
  trash: 'M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3',
  terminal: 'M4 5h16v14H4zM7 9l3 3-3 3M12 15h5',
  filter: 'M4 5h16l-6 8v6l-4-2v-4z',
  chevronLeft: 'M15 6l-6 6 6 6',
  box: 'M12 3l8 4.5v9L12 21l-8-4.5v-9zM4 7.5l8 4.5 8-4.5M12 12v9',
} as const;

const REUSED = { home: 'home', agent: 'agent', lock: 'lock', activity: 'activity' } as const;

export type CategoryIconName = keyof typeof OWN | keyof typeof REUSED;

export function CategoryIcon({ name, size = 20, label }: { name: CategoryIconName; size?: number; label?: string }) {
  if (name in REUSED) return <Icon name={REUSED[name as keyof typeof REUSED]} size={size} label={label} />;
  return (
    <svg
      className="om-icon"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      role={label ? 'img' : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      focusable="false"
    >
      <path d={OWN[name as keyof typeof OWN]} />
    </svg>
  );
}
