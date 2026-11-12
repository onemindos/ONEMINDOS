// SPDX-License-Identifier: Apache-2.0
// App categories and deployment classes from docs/design/TAXONOMY.md (§1, §2).
// The slugs are what the manifest and catalog API carry; names are what people read.
// Category icon paths are OneMind's own (TAXONOMY.md §1.2), drawn on the Icon.tsx grid.
import type { Tone } from '../tokens/tokens';

export const CATEGORY_SLUGS = [
  'home',
  'files',
  'media',
  'notes',
  'productivity',
  'communication',
  'ai',
  'automation',
  'network',
  'monitoring',
  'news',
  'developer',
  'family',
  'finance',
  'learning',
  'field',
] as const;
export type CategorySlug = (typeof CATEGORY_SLUGS)[number];

export interface CategoryInfo {
  slug: CategorySlug;
  name: string;
  /** SVG path data on a 24 x 24 grid (stroke icon, currentColor). */
  icon: string;
}

const P = {
  home: 'M4 11l8-7 8 7M6 9.5V20h12V9.5M10 20v-5h4v5',
  folder: 'M3 7a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z',
  play: 'M4 5h16v14H4zM10 9v6l5-3z',
  note: 'M6 3h9l4 4v14H6zM15 3v4h4M9 12h7M9 16h5',
  tasks: 'M4 6l1.5 1.5L8 5M4 12l1.5 1.5L8 11M4 18l1.5 1.5L8 17M11 6h9M11 12h9M11 18h9',
  chat: 'M4 5h16v10H9l-5 4zM8 9h8M8 12h5',
  agent: 'M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8zM18 16l.8 2.2L21 19l-2.2.8L18 22l-.8-2.2L15 19l2.2-.8z',
  flow: 'M4 4h6v5H4zM14 15h6v5h-6zM7 9v4h10v2',
  lock: 'M6 11h12v10H6zM8.5 11V8a3.5 3.5 0 0 1 7 0v3',
  activity: 'M3 12h4l3-7 4 14 3-7h4',
  radar: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM12 12l6-6',
  code: 'M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16',
  heart: 'M12 20s-7-4.5-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 10c0 5.5-7 10-7 10z',
  wallet: 'M4 7h15a1 1 0 0 1 1 1v11H4zM4 7l12-3v3M16 13h.01',
  book: 'M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0 0 4h13',
  radio: 'M12 12h.01M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.6 5.6a9 9 0 0 0 0 12.8M18.4 5.6a9 9 0 0 1 0 12.8',
};

/** In TAXONOMY.md §1 table order: daily essentials first, specialist categories last. */
export const CATEGORIES: readonly CategoryInfo[] = [
  { slug: 'home', name: 'Home & IoT', icon: P.home },
  { slug: 'files', name: 'Files & Photos', icon: P.folder },
  { slug: 'media', name: 'Media', icon: P.play },
  { slug: 'notes', name: 'Notes & Knowledge', icon: P.note },
  { slug: 'productivity', name: 'Productivity', icon: P.tasks },
  { slug: 'communication', name: 'Chat & Social', icon: P.chat },
  { slug: 'ai', name: 'AI & Agents', icon: P.agent },
  { slug: 'automation', name: 'Automation', icon: P.flow },
  { slug: 'network', name: 'Network & Security', icon: P.lock },
  { slug: 'monitoring', name: 'Monitoring', icon: P.activity },
  { slug: 'news', name: 'News & Intel', icon: P.radar },
  { slug: 'developer', name: 'Developer', icon: P.code },
  { slug: 'family', name: 'Family & Health', icon: P.heart },
  { slug: 'finance', name: 'Finance', icon: P.wallet },
  { slug: 'learning', name: 'Learning & Games', icon: P.book },
  { slug: 'field', name: 'Field & Robotics', icon: P.radio },
];

const BY_SLUG = new Map(CATEGORIES.map((c) => [c.slug, c]));

/** Legacy slugs still on `main` (TAXONOMY.md §1.3, "Slugs already on main"). */
const LEGACY: Record<string, CategorySlug> = {
  'home-automation': 'home',
  notifications: 'automation',
  security: 'network',
};

/** Normalise a catalog category to one of the 16 slugs; `undefined` when it cannot be placed. */
export function categoryOf(raw: string | undefined | null): CategoryInfo | undefined {
  if (!raw) return undefined;
  const slug = (BY_SLUG.has(raw as CategorySlug) ? raw : LEGACY[raw]) as CategorySlug | undefined;
  return slug ? BY_SLUG.get(slug) : undefined;
}

/** Deployment class (TAXONOMY.md §2): derived by the gateway, never typed by hand. */
export const DEPLOY_CLASSES = ['core', 'market-verified', 'market-community', 'list-only', 'private'] as const;
export type DeployClass = (typeof DEPLOY_CLASSES)[number];

export interface DeployClassInfo {
  label: string;
  /** Short words for a tile badge; empty when the class needs no badge on Home. */
  badge: string;
  tone: Tone;
  /** One sentence, as the TrustCard says it. */
  sentence: string;
}

export const DEPLOY_CLASS: Record<DeployClass, DeployClassInfo> = {
  core: { label: 'Part of OneMind', badge: 'System', tone: 'neutral', sentence: 'Part of OneMind. Updates with the system.' },
  'market-verified': { label: 'Verified', badge: '', tone: 'ok', sentence: 'From the Market; passed every OneMind check.' },
  'market-community': { label: 'Community', badge: 'Community', tone: 'neutral', sentence: 'From the Market; not fully checked by OneMind.' },
  'list-only': { label: 'Link only', badge: 'Link only', tone: 'info', sentence: 'Listed only; OneMind does not ship it.' },
  private: { label: 'Private', badge: 'Your own', tone: 'info', sentence: 'Your own deployment, only on this OneMind.' },
};

/** Home's "Show" filter groups the classes the way a person thinks of them. */
export const SOURCE_FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'market', label: 'From the Market', classes: ['market-verified', 'market-community'] as DeployClass[] },
  { id: 'private', label: 'Your own', classes: ['private'] as DeployClass[] },
  { id: 'core', label: 'System', classes: ['core'] as DeployClass[] },
] as const;
export type SourceFilter = (typeof SOURCE_FILTERS)[number]['id'];
