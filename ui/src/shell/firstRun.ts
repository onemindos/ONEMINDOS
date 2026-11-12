// SPDX-License-Identifier: Apache-2.0
// First-run wizard logic (backlog ONB-P1, ONB-B1, ONB-B2; parity item PU-05).
// Pure functions: the screens render them, `onemind init` (planned, ONB-B1) runs the same
// steps headless. Starter apps are not installed by the wizard: each becomes an `app.install`
// request the owner approves on Home after setup (P1).
import type { CSSProperties } from 'react';
import { ACCENTS as APPEARANCE_ACCENTS, ACCENT_IDS as APPEARANCE_ACCENT_IDS, presetAccent, type AccentId as AppearanceAccentId } from '../customize/accents';
import type { ThemeChoice } from '../lib/theme';
import { deployClass, type CategorySlug, type DeployClass } from './taxonomy';

export const ONBOARDING_STEPS = [
  { id: 'box', title: 'Name your box', short: 'Box' },
  { id: 'owner', title: 'Create the owner', short: 'Owner' },
  { id: 'appearance', title: 'Make it yours', short: 'Look' },
  { id: 'apps', title: 'Pick starter apps', short: 'Apps' },
  { id: 'backups', title: 'Protect your data', short: 'Backups' },
  { id: 'done', title: 'Ready', short: 'Done' },
] as const;
export type StepId = (typeof ONBOARDING_STEPS)[number]['id'];

// ---------- accents ----------
// The presets are the Appearance settings' own (src/customize), so a colour picked here is one
// Settings knows. presetAccent() derives each set and guarantees AA contrast in both themes.
export const ACCENT_IDS = APPEARANCE_ACCENT_IDS;
export type AccentId = AppearanceAccentId;
export const accentName = (id: AccentId): string => APPEARANCE_ACCENTS[id].name;

/**
 * CSS variables that re-tint a subtree with an accent. `light-dark()` follows the
 * `color-scheme` the token sheet sets for System, Light and Dark. Teal returns {} (the default).
 */
export function accentVars(id: AccentId): CSSProperties {
  if (id === 'teal') return {};
  const { light: l, dark: d } = presetAccent(id);
  const pair = (k: keyof typeof l.set) => `light-dark(${l.set[k]}, ${d.set[k]})`;
  return {
    '--om-color-accent': pair('accent'),
    '--om-color-accent-hover': pair('hover'),
    '--om-color-accent-text': pair('text'),
    '--om-color-accent-soft': pair('soft'),
  } as CSSProperties;
}

// ---------- draft ----------
export type PasskeyState = 'none' | 'waiting' | 'registered' | 'failed';
export type BackupDestination = 'usb' | 'peer' | 's3' | 'later';

export interface OnboardingDraft {
  boxName: string;
  timeZone: string;
  ownerName: string;
  passkey: PasskeyState;
  theme: ThemeChoice;
  accent: AccentId;
  starterApps: string[];
  backup: { destination: BackupDestination; kitSaved: boolean };
}

export function emptyDraft(timeZone = 'UTC'): OnboardingDraft {
  return {
    boxName: '',
    timeZone,
    ownerName: '',
    passkey: 'none',
    theme: 'system',
    accent: 'teal',
    starterApps: [],
    backup: { destination: 'usb', kitSaved: false },
  };
}

/** The box name becomes its LAN name (`<name>.local`), so it follows DNS label rules (RFC 1123). */
export function validateBoxName(name: string): string | null {
  if (!name) return 'Give your box a name.';
  if (name.length > 63) return 'Use 63 characters or fewer.';
  if (!/^[a-z0-9-]+$/.test(name)) return 'Use lowercase letters, numbers and hyphens only.';
  if (name.startsWith('-') || name.endsWith('-')) return 'Start and end with a letter or number.';
  return null;
}

/** "Dana's Home Hub" → "danas-home-hub". */
export function slugifyBoxName(input: string): string {
  return input
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[̀-ͯ']/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 63)
    .replace(/-+$/, '');
}

/** Why the person cannot continue yet; empty means they can. */
export function stepIssues(step: StepId, d: OnboardingDraft): string[] {
  const out: string[] = [];
  if (step === 'box') {
    const e = validateBoxName(d.boxName);
    if (e) out.push(e);
    if (!d.timeZone) out.push('Choose a time zone.');
  }
  if (step === 'owner') {
    if (!d.ownerName.trim()) out.push('Enter your name.');
    if (d.ownerName.trim().length > 64) out.push('Use 64 characters or fewer for your name.');
    if (d.passkey !== 'registered') out.push('Create a passkey. The owner signs in with it; there is no password.');
  }
  if (step === 'backups' && !d.backup.kitSaved) {
    out.push('Save the emergency kit first. Without it nobody can recover this box.');
  }
  return out;
}

/** Steps that must be done before Finish; the emergency kit cannot be skipped (ONB-B2). */
export function finishIssues(d: OnboardingDraft): Array<{ step: StepId; issue: string }> {
  return ONBOARDING_STEPS.flatMap((s) => stepIssues(s.id, d).map((issue) => ({ step: s.id, issue })));
}

/** Furthest step a person may jump to: every step before it must be complete. */
export function furthestReachable(d: OnboardingDraft): number {
  for (let i = 0; i < ONBOARDING_STEPS.length; i++) {
    if (stepIssues(ONBOARDING_STEPS[i]!.id, d).length > 0) return i;
  }
  return ONBOARDING_STEPS.length - 1;
}

/** The requests the wizard creates on Finish (contract §3). Nothing installs without approval. */
export function finishRequests(d: OnboardingDraft): Array<{ type: 'app.install'; params: { app_id: string } }> {
  return d.starterApps.map((app_id) => ({ type: 'app.install', params: { app_id } }));
}

const q = (s: string) => (/^[\w@%+=:,./-]+$/.test(s) ? s : `'${s.replace(/'/g, `'\\''`)}'`);

/** The headless twin of this wizard (ONB-B1, planned CLI verb). The passkey step stays interactive. */
export function initCommand(d: OnboardingDraft): string {
  const parts = ['onemind init', `--name ${q(d.boxName || '<name>')}`, `--timezone ${q(d.timeZone)}`, `--owner ${q(d.ownerName.trim() || '<your name>')}`];
  if (d.theme !== 'system') parts.push(`--theme ${d.theme}`);
  if (d.accent !== 'teal') parts.push(`--accent ${d.accent}`);
  if (d.backup.destination !== 'later') parts.push(`--backup ${d.backup.destination}`);
  if (d.starterApps.length) parts.push(`--request-apps ${d.starterApps.join(',')}`);
  return parts.join(' ');
}

// ---------- starter apps ----------
export interface StarterApp {
  id: string;
  name: string;
  tagline: string;
  category: CategorySlug;
  deployClass: DeployClass;
  plugin?: boolean;
  minMemoryMb: number;
  /** In the edition's launch set (TAXONOMY §4 "Recommended for this box"). */
  recommended?: boolean;
}

/** Apps the wizard may offer: Market classes a person can request (no core, link-only or private). */
export function offerable(apps: StarterApp[]): StarterApp[] {
  return apps.filter((a) => deployClass(a.deployClass).requestable && a.deployClass !== 'private');
}

/** Category counts in TAXONOMY order, only categories that have offerable apps. */
export function categoryCounts(apps: StarterApp[], order: readonly CategorySlug[]): Array<{ slug: CategorySlug; count: number }> {
  return order.map((slug) => ({ slug, count: apps.filter((a) => a.category === slug).length })).filter((c) => c.count > 0);
}

export function toggleApp(selected: string[], id: string): string[] {
  return selected.includes(id) ? selected.filter((x) => x !== id) : [...selected, id];
}

/** Total memory the chosen apps ask for, so the screen can compare it with the hub's free memory. */
export function selectedMemoryMb(apps: StarterApp[], selected: string[]): number {
  return apps.filter((a) => selected.includes(a.id)).reduce((s, a) => s + a.minMemoryMb, 0);
}
