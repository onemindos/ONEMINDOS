// SPDX-License-Identifier: Apache-2.0
// Shell view of the app taxonomy (docs/design/TAXONOMY.md §1 and §2). The data lives in
// src/store/taxonomy.ts so the Market, the palette and onboarding name categories and classes
// the same way; this adapter only adds shell icon names and the "can be requested" rule.
import type { Tone } from '../tokens/tokens';
import { CATEGORIES as STORE_CATEGORIES, DEPLOY_CLASSES } from '../store/taxonomy';
import type { CategorySlug, DeployClass } from '../store/types';
import type { ShellIconName } from './icons';

export type { CategorySlug, DeployClass };

export interface ShellCategory {
  slug: CategorySlug;
  name: string;
  icon: ShellIconName;
}

/** TAXONOMY §1 order: daily essentials first, specialist categories last. */
export const SHELL_CATEGORIES: readonly ShellCategory[] = STORE_CATEGORIES.map((c) => ({ slug: c.slug, name: c.label, icon: c.icon as ShellIconName }));
export const CATEGORY_ORDER: readonly CategorySlug[] = SHELL_CATEGORIES.map((c) => c.slug);

const BY_SLUG = new Map(SHELL_CATEGORIES.map((c) => [c.slug as string, c]));

/** The category for a slug; legacy free text ("home-automation") returns undefined, never a guess. */
export function category(slug: string): ShellCategory | undefined {
  return BY_SLUG.get(slug);
}

export interface ClassInfo {
  label: string;
  tone: Tone;
  sentence: string;
  /** A person can request it from the shell (Market apps and private deployments). */
  requestable: boolean;
}

export function deployClass(cls: DeployClass): ClassInfo {
  const c = DEPLOY_CLASSES[cls];
  return { label: c.label, tone: c.tone, sentence: c.sentence, requestable: c.action === 'request-install' || c.action === 'request-deploy' };
}

/** Pill text for a class plus the plugin flag: "Plugin · Verified" (TAXONOMY §2). */
export function deployClassLabel(cls: DeployClass, plugin = false): string {
  return plugin ? `Plugin · ${DEPLOY_CLASSES[cls].label}` : DEPLOY_CLASSES[cls].label;
}
