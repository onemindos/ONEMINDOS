// SPDX-License-Identifier: Apache-2.0
// App categories, deployment classes and node roles from docs/design/TAXONOMY.md (§1, §2, §3.2).
// Labels only; the slugs are what the manifest and GET /v1/apps carry.
import type { Tone } from '../tokens/tokens';

export const CATEGORY_LABEL = {
  home: 'Home & IoT',
  files: 'Files & Photos',
  media: 'Media',
  notes: 'Notes & Knowledge',
  productivity: 'Productivity',
  communication: 'Chat & Social',
  ai: 'AI & Agents',
  automation: 'Automation',
  network: 'Network & Security',
  monitoring: 'Monitoring',
  news: 'News & Intel',
  developer: 'Developer',
  family: 'Family & Health',
  finance: 'Finance',
  learning: 'Learning & Games',
  field: 'Field & Robotics',
} as const;
export type CategorySlug = keyof typeof CATEGORY_LABEL;
/** Table order of TAXONOMY §1 (the founder's daily essentials first). */
export const CATEGORY_ORDER = Object.keys(CATEGORY_LABEL) as CategorySlug[];

export type DeployClass = 'core' | 'market-verified' | 'market-community' | 'list-only' | 'private';
/**
 * Pill per class (TAXONOMY §2). `private` uses neutral, not the violet the taxonomy suggests:
 * TOKENS.md reserves the agent colour for anything an AI did or asked.
 */
export const DEPLOY_CLASS: Record<DeployClass, { label: string; tone: Tone; sentence: string }> = {
  core: { label: 'Part of OneMind', tone: 'neutral', sentence: 'Installed with the system and updated with it.' },
  'market-verified': { label: 'Verified', tone: 'ok', sentence: 'Passed every Market check; scanned in the last 7 days.' },
  'market-community': { label: 'Community', tone: 'neutral', sentence: 'Listed in the Market but not fully checked by OneMind.' },
  'list-only': { label: 'Link only', tone: 'info', sentence: 'OneMind may not ship it; you get it from upstream.' },
  private: { label: 'Private', tone: 'neutral', sentence: 'Your own deployment, only on this box.' },
};
/** Order in which updates and usage are grouped: what OneMind vouches for most comes first. */
export const DEPLOY_ORDER: DeployClass[] = ['core', 'market-verified', 'market-community', 'private', 'list-only'];

export type NodeRole = 'hub' | 'worker' | 'leaf';
export const NODE_ROLE: Record<NodeRole, { label: string; sentence: string }> = {
  hub: { label: 'Hub', sentence: 'The main node: gateway, bus, and apps that need one stable home-network address.' },
  worker: { label: 'Worker', sentence: 'Runs apps. Heavy apps (local AI, large databases) prefer workers so the hub stays responsive.' },
  leaf: { label: 'Leaf', sentence: 'A small or remote machine on the message bus only. Runs device and field adapters, not Market apps.' },
};
