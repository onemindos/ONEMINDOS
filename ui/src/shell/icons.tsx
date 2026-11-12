// SPDX-License-Identifier: Apache-2.0
// Shell icons: the library set (components/Icon.tsx) plus the twelve category icons from
// docs/design/TAXONOMY.md §1.2 and a few shell glyphs. All drawn for OneMind on the same
// 24 px grid, 1.75 stroke, round caps and joins, currentColor. No third-party icon was used.
// When the category icons move into Icon.tsx, this file shrinks to a re-export.
import { Icon, ICON_NAMES, type IconName } from '../components/Icon';

const EXTRA = {
  // TAXONOMY.md §1.2 category icons
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
  // shell glyphs
  command: 'M9 9V6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z',
  inbox: 'M4 13l2.5-8h11L20 13v6H4zM4 13h5l1 2h4l1-2h5',
  enter: 'M20 5v7H6M10 8l-4 4 4 4',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  key: 'M8 15a4 4 0 1 1 3.5-6H21v3h-2v3h-3v-3h-4.5A4 4 0 0 1 8 15z',
  disk: 'M4 6h16v12H4zM4 14h16M16 17h.01',
  cloud: 'M7 18a4 4 0 0 1-.5-8A6 6 0 0 1 18 9a4.5 4.5 0 0 1 0 9z',
  download: 'M12 4v11M7 10l5 5 5-5M5 20h14',
  offline: 'M4 4l16 16M8.5 16.5a5 5 0 0 1 7 0M5 12.5a10 10 0 0 1 4-2.3M14.5 10.2a10 10 0 0 1 4.5 2.3M12 20h.01',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3c2.5 2.5 3.5 5.5 3.5 9s-1 6.5-3.5 9c-2.5-2.5-3.5-5.5-3.5-9S9.5 5.5 12 3z',
  undo: 'M9 14L4 9l5-5M4 9h10a6 6 0 0 1 0 12h-3',
  brush: 'M12 21a9 9 0 1 1 9-9c0 2-1.5 3-3 3h-2a2 2 0 0 0-1.5 3.3c.6.8.1 2.7-2.5 2.7zM7.5 11h.01M10 7.5h.01M14.5 7.5h.01',
  passkey: 'M12 11v3c0 2.5-.8 4.7-2 6.5M8.5 8.8A4 4 0 0 1 16 11v2c0 2-.3 3.8-1 5.5M5 12a7 7 0 0 1 12.5-4.3M19 11.5V13c0 1.5-.2 3-.5 4.3',
  box: 'M4 8l8-4 8 4v8l-8 4-8-4zM4 8l8 4 8-4M12 12v8',
  eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z',
} as const;

export type ExtraIconName = keyof typeof EXTRA;
export type ShellIconName = IconName | ExtraIconName;
export const SHELL_ICON_NAMES = [...ICON_NAMES, ...(Object.keys(EXTRA) as ExtraIconName[])] as ShellIconName[];

export interface ShellIconProps {
  name: ShellIconName;
  size?: number;
  /** Accessible name; without it the icon is decorative. */
  label?: string;
  className?: string;
}

function isExtra(name: ShellIconName): name is ExtraIconName {
  return name in EXTRA;
}

export function ShellIcon({ name, size = 20, label, className }: ShellIconProps) {
  if (!isExtra(name)) return <Icon name={name} size={size} label={label} className={className} />;
  return (
    <svg
      className={className ? `om-icon ${className}` : 'om-icon'}
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
      <path d={EXTRA[name]} />
    </svg>
  );
}
