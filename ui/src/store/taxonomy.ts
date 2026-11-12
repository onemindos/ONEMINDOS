// SPDX-License-Identifier: Apache-2.0
// The Market taxonomy as data (docs/design/TAXONOMY.md §1 and §2). Order is the table order.
// Labels here are the only place the UI names a category or class, so CLI, agents and UI agree.
import type { Tone } from '../tokens/tokens';
import type { CategoryIconName } from './CategoryIcon';
import type { CategorySlug, DeployClass, DeviceClass, Exposure, LicenceClass } from './types';

export interface CategoryInfo {
  slug: CategorySlug;
  label: string;
  icon: CategoryIconName;
  /** Closed sub-tag list (TAXONOMY §1.1 rule 2). */
  tags: readonly string[];
}

export const CATEGORIES: readonly CategoryInfo[] = [
  { slug: 'home', label: 'Home & IoT', icon: 'home', tags: ['hub', 'mqtt', 'zigbee', 'zwave', 'matter', 'cameras', 'energy', 'firmware', 'industrial', '3d-printing'] },
  { slug: 'files', label: 'Files & Photos', icon: 'folder', tags: ['cloud', 'photos', 'sync', 'sharing', 'documents', 'backup', 'storage', 'calendar-contacts', 'convert'] },
  { slug: 'media', label: 'Media', icon: 'play', tags: ['video', 'music', 'books', 'podcasts', 'downloads', 'indexers', 'requests', 'live', 'transcode'] },
  { slug: 'notes', label: 'Notes & Knowledge', icon: 'note', tags: ['notes', 'wiki', 'bookmarks', 'read-later', 'whiteboard', 'docs'] },
  { slug: 'productivity', label: 'Productivity', icon: 'tasks', tags: ['office', 'tasks', 'scheduling', 'time', 'forms', 'business', 'helpdesk', 'website', 'shop', 'signing', 'utility'] },
  { slug: 'communication', label: 'Chat & Social', icon: 'chat', tags: ['chat', 'matrix', 'email', 'video-calls', 'voice', 'forum', 'fediverse', 'newsletter', 'bridge'] },
  { slug: 'ai', label: 'AI & Agents', icon: 'agent', tags: ['chat', 'llm-runtime', 'agents', 'rag', 'coding', 'image', 'speech', 'audio', 'ocr', 'search', 'translation', 'training', 'gateway'] },
  { slug: 'automation', label: 'Automation', icon: 'flow', tags: ['workflows', 'notifications', 'jobs'] },
  { slug: 'network', label: 'Network & Security', icon: 'lock', tags: ['passwords', 'sso', 'vpn', 'dns', 'ddns', 'proxy', 'remote-access', 'firewall', 'speedtest', 'tor'] },
  { slug: 'monitoring', label: 'Monitoring', icon: 'activity', tags: ['uptime', 'metrics', 'logs', 'analytics', 'dashboards', 'admin'] },
  { slug: 'news', label: 'News & Intel', icon: 'radar', tags: ['rss', 'archive', 'change-detection', 'osint', 'search'] },
  { slug: 'developer', label: 'Developer', icon: 'code', tags: ['git', 'ci', 'ide', 'database', 'api-backend', 'low-code', 'containers', 'search-engine', 'design', 'vm-desktop', 'tools'] },
  { slug: 'family', label: 'Family & Health', icon: 'heart', tags: ['recipes', 'groceries', 'inventory', 'genealogy', 'travel', 'health', 'fitness', 'habits', 'vehicles', 'garden'] },
  { slug: 'finance', label: 'Finance', icon: 'wallet', tags: ['budget', 'investing', 'invoicing', 'bitcoin', 'lightning', 'crypto', 'trading'] },
  { slug: 'learning', label: 'Learning & Games', icon: 'book', tags: ['courses', 'offline-knowledge', 'languages', 'games', 'game-server', 'emulation'] },
  { slug: 'field', label: 'Field & Robotics', icon: 'radio', tags: ['mesh', 'tak', 'radio', 'gps', 'maps', 'robotics'] },
];

export const CATEGORY_BY_SLUG = Object.fromEntries(CATEGORIES.map((c) => [c.slug, c])) as Record<CategorySlug, CategoryInfo>;

export interface DeployClassInfo {
  label: string;
  /** Pill tone. Core is neutral, verified ok, community neutral, list-only info, private agent-free outline. */
  tone: Tone;
  /** One sentence the UI shows next to the pill. */
  sentence: string;
  /** The single primary action the card offers. */
  action: 'request-install' | 'upstream' | 'request-deploy' | 'none';
}

export const DEPLOY_CLASSES: Record<DeployClass, DeployClassInfo> = {
  core: { label: 'Part of OneMind', tone: 'neutral', sentence: 'Installed with the system and updated with it.', action: 'none' },
  'market-verified': { label: 'Verified', tone: 'ok', sentence: 'Passed every Market check: licence, pinning, vulnerabilities, malware, secrets and a smoke test.', action: 'request-install' },
  'market-community': { label: 'Community', tone: 'neutral', sentence: 'Listed in the Market, but not fully checked by OneMind.', action: 'request-install' },
  'list-only': { label: 'Link only', tone: 'info', sentence: 'Listed for completeness. OneMind does not ship or install it.', action: 'upstream' },
  private: { label: 'Private', tone: 'neutral', sentence: 'Only on this OneMind. Never sent to the public index.', action: 'request-deploy' },
};

/** Classes a person can filter by in the Market (Core never appears in browsing, TAXONOMY §2). */
export const BROWSABLE_CLASSES: readonly DeployClass[] = ['market-verified', 'market-community', 'list-only', 'private'];

export const LICENCE_CLASSES: Record<LicenceClass, { label: string; sentence: string }> = {
  L1: { label: 'Permissive', sentence: 'Permissive licence (MIT, BSD, Apache-2.0 and similar).' },
  L2: { label: 'Copyleft', sentence: 'Copyleft licence that allows OneMind to run it (GPL, AGPL, MPL).' },
  L3: { label: 'Source-available', sentence: 'Source-available: the licence does not allow OneMind to ship it.' },
  'L?': { label: 'Unclear licence', sentence: 'The licence is unclear, so OneMind does not ship it.' },
};

export const DEVICE_LABEL: Record<DeviceClass, string> = {
  'usb-serial': 'a USB serial device',
  zigbee: 'a Zigbee USB radio',
  zwave: 'a Z-Wave USB radio',
  thread: 'a Thread radio',
  bluetooth: 'Bluetooth',
  sdr: 'a software-defined radio',
  lora: 'a LoRa radio',
  camera: 'a camera',
  coral: 'a Coral accelerator',
  gpio: 'GPIO pins',
};

export const EXPOSURE_LABEL: Record<Exposure, string> = {
  lan: 'your home network',
  mesh: 'your home network and your devices away from home',
  public: 'the internet (only after a separate approval)',
};

export function categoryLabel(slug: string): string {
  return CATEGORY_BY_SLUG[slug as CategorySlug]?.label ?? 'Uncategorised';
}

/** True when `tag` is on the category's closed list (the validator's rule, TAXONOMY §5). */
export function isKnownTag(slug: CategorySlug, tag: string): boolean {
  return CATEGORY_BY_SLUG[slug]?.tags.includes(tag) ?? false;
}
